import io
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import tensorflow as tf
from PIL import Image, UnidentifiedImageError

from app.services.vlm_detector import identify_ingredients

try:
    from app.services.freshness_estimator import FreshnessAndExpiryEstimator, get_freshness_estimator
    from app.services.item_segmenter import ItemSegmenter, calculate_iou, get_item_segmenter
except ImportError:
    from backend.app.services.freshness_estimator import FreshnessAndExpiryEstimator, get_freshness_estimator
    from backend.app.services.item_segmenter import ItemSegmenter, calculate_iou, get_item_segmenter

logger = logging.getLogger(__name__)

# Base directory resolved relative to this file: backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_MODEL_PATH = BACKEND_DIR / "models" / "dishgenie_cnn.keras"
DEFAULT_CLASSES_PATH = BACKEND_DIR / "models" / "dishgenie_classes.json"


class VisionService:
    """
    Reusable Computer Vision Service for DishGenie.
    Loads the trained CNN and class mappings once at startup and performs
    validated preprocessing, multi-item OpenCV segmentation, CNN classification,
    freshness grading, item counting, and visual annotation.
    """

    def __init__(
        self,
        model_path: Optional[Union[str, Path]] = None,
        classes_path: Optional[Union[str, Path]] = None,
    ):
        self.model_path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
        self.classes_path = Path(classes_path) if classes_path else DEFAULT_CLASSES_PATH

        self.model: Optional[tf.keras.Model] = None
        self.class_names: List[str] = []

        self.segmenter: ItemSegmenter = get_item_segmenter()
        self.freshness_estimator: FreshnessAndExpiryEstimator = get_freshness_estimator()

        # Load resources immediately to ensure fail-fast behavior at startup
        self._load_resources()

    def _load_resources(self) -> None:
        """
        Validates and loads the class names JSON and CNN model once.
        Fails fast with clear descriptive exceptions if missing or corrupted.
        """
        # 1. Validate class file existence
        if not self.classes_path.exists():
            raise FileNotFoundError(
                f"[VisionService] Class names JSON not found at: {self.classes_path.resolve()}"
            )

        # 2. Parse class names JSON (supports both {"class": idx} dict and ["class", ...] list)
        try:
            with open(self.classes_path, "r", encoding="utf-8") as f:
                raw_classes = json.load(f)

            if isinstance(raw_classes, dict):
                first_key, first_val = next(iter(raw_classes.items()))
                if isinstance(first_val, int):
                    sorted_items = sorted(raw_classes.items(), key=lambda x: int(x[1]))
                    self.class_names = [str(k) for k, _ in sorted_items]
                else:
                    sorted_items = sorted(raw_classes.items(), key=lambda x: int(x[0]))
                    self.class_names = [str(v) for _, v in sorted_items]
            elif isinstance(raw_classes, list):
                self.class_names = [str(c) for c in raw_classes]
            else:
                raise ValueError("Classes JSON must contain a list of strings or a dict mapping classes to indices.")

            if len(self.class_names) == 0:
                raise ValueError("Parsed class names list cannot be empty.")

            logger.info(f"[VisionService] Loaded {len(self.class_names)} classes.")
        except Exception as e:
            raise ValueError(
                f"[VisionService] Failed to load/parse class names from {self.classes_path}: {e}"
            ) from e

        # 3. Validate model file existence
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"[VisionService] CNN model file not found at: {self.model_path.resolve()}"
            )

        # 4. Load Keras model
        try:
            logger.info(f"[VisionService] Loading CNN model from: {self.model_path.resolve()}...")
            self.model = tf.keras.models.load_model(str(self.model_path))
            logger.info("[VisionService] CNN model loaded successfully into memory.")
        except Exception as e:
            raise RuntimeError(
                f"[VisionService] Failed to load CNN model from {self.model_path}: {e}"
            ) from e

    def _status(self, expiry_days: int, name: str) -> str:
        """Use First only when truly close to expiry; otherwise relative to the item's own shelf life (a 7-day tomato at 5 days is Fresh)."""
        if expiry_days <= 3:
            return "Use First"
        base = self.freshness_estimator.get_base_shelf_life(name)
        return "Fresh" if expiry_days > 7 or expiry_days >= 0.7 * base else "Medium"

    @property
    def is_available(self) -> bool:
        """Returns True if the model and classes are loaded and ready."""
        return self.model is not None and len(self.class_names) > 0

    def preprocess_image(self, image_input: Union[bytes, io.BytesIO, Image.Image, np.ndarray]) -> np.ndarray:
        """
        Preprocesses an image to match the CNN input shape requirements:
        1. Convert image to RGB
        2. Resize to 224 x 224
        3. Convert to NumPy array
        4. Add batch dimension: shape (1, 224, 224, 3)
        NOTE: Does NOT divide by 255 because the CNN model architecture contains
        its own internal Rescaling(1/255) layer.
        """
        if isinstance(image_input, bytes):
            if len(image_input) == 0:
                raise ValueError("Uploaded image file is empty.")
            try:
                pil_img = Image.open(io.BytesIO(image_input))
            except UnidentifiedImageError as e:
                raise ValueError("Uploaded file is not a valid or supported image.") from e
        elif isinstance(image_input, io.BytesIO):
            try:
                image_input.seek(0)
                pil_img = Image.open(image_input)
            except UnidentifiedImageError as e:
                raise ValueError("Provided stream is not a valid or supported image.") from e
        elif isinstance(image_input, Image.Image):
            pil_img = image_input
        elif isinstance(image_input, np.ndarray):
            pil_img = Image.fromarray(image_input)
        else:
            raise ValueError(f"Unsupported image input type: {type(image_input)}")

        # Convert to RGB (handles RGBA, grayscale, CMYK, P with transparency, etc.)
        if pil_img.mode in ("RGBA", "LA") or (pil_img.mode == "P" and "transparency" in pil_img.info):
            rgb_img = pil_img.convert("RGBA").convert("RGB")
        else:
            rgb_img = pil_img.convert("RGB")

        # Aspect-ratio-preserving resize with neutral centered padding
        orig_w, orig_h = rgb_img.size
        scale = 224.0 / max(orig_w, orig_h)
        new_w = max(1, int(round(orig_w * scale)))
        new_h = max(1, int(round(orig_h * scale)))
        scaled_img = rgb_img.resize((new_w, new_h), Image.Resampling.BILINEAR)

        # 224 x 224 canvas with neutral gray padding
        canvas = Image.new("RGB", (224, 224), (128, 128, 128))
        canvas.paste(scaled_img, ((224 - new_w) // 2, (224 - new_h) // 2))

        # Convert to NumPy array
        img_array = np.array(canvas, dtype=np.float32)

        # Add batch dimension -> (1, 224, 224, 3)
        batched_array = np.expand_dims(img_array, axis=0)

        return batched_array

    def _infer_array(
        self,
        image_array: np.ndarray,
        top_k: int = 3,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Internal helper: executes CNN forward pass on a preprocessed (1, 224, 224, 3) batch.
        """
        try:
            raw_predictions = self.model.predict(image_array, verbose=0)
        except Exception as e:
            logger.error(f"[VisionService] Inference execution failed: {e}", exc_info=True)
            raise RuntimeError(f"Model inference failed during computation: {e}") from e

        probabilities = raw_predictions[0]

        # Apply softmax if output is logits
        if np.max(probabilities) > 1.0 or np.min(probabilities) < 0.0 or not np.isclose(np.sum(probabilities), 1.0, atol=0.05):
            exp_preds = np.exp(probabilities - np.max(probabilities))
            probabilities = exp_preds / np.sum(exp_preds)

        top_indices = np.argsort(probabilities)[::-1][:top_k]
        top_predictions: List[Dict[str, Any]] = []
        for idx in top_indices:
            idx_int = int(idx)
            class_name = (
                self.class_names[idx_int]
                if idx_int < len(self.class_names)
                else f"Class_{idx_int}"
            )
            conf = float(np.clip(probabilities[idx_int], 0.0, 1.0))
            top_predictions.append({
                "name": class_name,
                "confidence": round(conf, 4),
            })

        primary_prediction = top_predictions[0] if top_predictions else {
            "name": "Unknown",
            "confidence": 0.0,
        }
        return primary_prediction, top_predictions

    def predict(
        self,
        image_input: Union[bytes, io.BytesIO, Image.Image],
        top_k: int = 3,
        min_confidence: float = 0.50,
    ) -> Dict[str, Any]:
        """
        Full Multi-Object Detection, Counting, and Expiry Estimation Pipeline:
        1. Custom OpenCV contour segmentation & bounding box extraction
        2. Fallback to full-image inference for single-item images
        3. Sequential CNN inference on cropped bounding boxes
        4. Confidence thresholding (probability >= 0.50) to ignore background noise
        5. Visual freshness grading & shelf life calculation for each detected crop
        6. Item counting & inventory aggregation
        7. Visual annotation with bounding boxes, names, and expiry days
        """
        if not self.is_available:
            raise RuntimeError("VisionService is not initialized or model is unavailable.")

        # 1. Load PIL Image and extract RGB NumPy representation
        if isinstance(image_input, bytes):
            if len(image_input) == 0:
                raise ValueError("Uploaded image file is empty.")
            try:
                pil_img = Image.open(io.BytesIO(image_input))
            except UnidentifiedImageError as e:
                raise ValueError("Uploaded file is not a valid or supported image.") from e
        elif isinstance(image_input, io.BytesIO):
            try:
                image_input.seek(0)
                pil_img = Image.open(image_input)
            except UnidentifiedImageError as e:
                raise ValueError("Provided stream is not a valid or supported image.") from e
        elif isinstance(image_input, Image.Image):
            pil_img = image_input
        elif isinstance(image_input, np.ndarray):
            pil_img = Image.fromarray(image_input)
        else:
            raise ValueError(f"Unsupported image input type: {type(image_input)}")

        rgb_img = pil_img.convert("RGB")
        image_rgb = np.array(rgb_img)
        img_h, img_w = image_rgb.shape[:2]

        # 1. Global Full-Image CNN Inference First (Anchor Predictions)
        full_batched = self.preprocess_image(pil_img)
        primary_full, full_top_candidates = self._infer_array(full_batched, top_k=max(5, top_k))
        anchor_class = primary_full["name"]
        anchor_confidence = float(primary_full["confidence"])

        full_top_names = [c["name"] for c in full_top_candidates]
        full_top3_names = set(full_top_names[:3])
        full_top5_names = set(full_top_names[:5])

        # 2. Segment items using OpenCV contour discovery & pile assessment
        candidate_boxes, pile_info = self.segmenter.segment_with_pile_info(image_rgb)
        is_pile = pile_info.get("is_pile", False)
        peak_count = pile_info.get("peak_count", len(candidate_boxes))

        detections: List[Dict[str, Any]] = []
        is_multi_item = len(candidate_boxes) > 1 or (
            len(candidate_boxes) == 1 and candidate_boxes[0] != (0, 0, img_w, img_h)
        )

        # 3. Classify candidate boxes with Square Context Padding & Global-Local Consistency Gate
        if is_multi_item and candidate_boxes != [(0, 0, img_w, img_h)]:
            logger.info(
                f"[VisionService] Processing {len(candidate_boxes)} candidate crops "
                f"(is_pile={is_pile}, peaks={peak_count}, anchor={anchor_class})..."
            )
            for box in candidate_boxes:
                bx, by, bw, bh = box
                # Extract crop with 15% context padding
                crop = self.segmenter.get_square_context_crop(image_rgb, box, margin_ratio=0.15)
                if crop.shape[0] < 20 or crop.shape[1] < 20:
                    continue

                crop_batched = self.preprocess_image(crop)
                crop_prim, _ = self._infer_array(crop_batched, top_k=1)

                # Check spatial separation for this box
                # A box is spatially separated if its IoU with every other candidate box is < 0.15
                is_spatially_separated = True
                for other_box in candidate_boxes:
                    if other_box != box and calculate_iou(box, other_box) >= 0.15:
                        is_spatially_separated = False
                        break

                # Stage 2: 247-Class Custom CNN Classification with Global-Local Consistency Gate
                if is_spatially_separated:
                    # Spatially separated items (e.g. Tomato + Potato side by side)
                    # Never overwrite if crop's own CNN confidence is >= 55%
                    if crop_prim["confidence"] >= 0.55:
                        assigned_name = crop_prim["name"]
                        assigned_conf = crop_prim["confidence"]
                    elif crop_prim["name"] in full_top3_names:
                        assigned_name = crop_prim["name"]
                        assigned_conf = crop_prim["confidence"]
                    else:
                        assigned_name = anchor_class
                        assigned_conf = anchor_confidence
                elif is_pile:
                    # Homogeneous pile (overlapping boxes):
                    # If crop prediction is low confidence or conflicts with Global Top-1, snap to Global Top-1
                    if crop_prim["name"] == anchor_class and crop_prim["confidence"] >= 0.60:
                        assigned_name = anchor_class
                        assigned_conf = crop_prim["confidence"]
                    else:
                        logger.info(
                            f"[VisionService] Snapping pile crop '{crop_prim['name']}' ({crop_prim['confidence']:.2f}) "
                            f"to Global Top-1 Anchor '{anchor_class}'."
                        )
                        assigned_name = anchor_class
                        assigned_conf = anchor_confidence
                else:
                    if crop_prim["name"] in full_top3_names:
                        assigned_name = crop_prim["name"]
                        assigned_conf = crop_prim["confidence"]
                    elif crop_prim["confidence"] >= 0.55:
                        assigned_name = crop_prim["name"]
                        assigned_conf = crop_prim["confidence"]
                    else:
                        assigned_name = anchor_class
                        assigned_conf = anchor_confidence

                freshness = self.freshness_estimator.analyze_crop(crop, assigned_name)
                exp_days = freshness["estimated_expiry_days"]
                det_status = self._status(exp_days, assigned_name)
                detections.append({
                    "ingredient": assigned_name,
                    "confidence": assigned_conf,
                    "box": {"x": int(bx), "y": int(by), "w": int(bw), "h": int(bh)},
                    "freshness_score": freshness["freshness_score"],
                    "expiry_days": exp_days,
                    "status": det_status,
                })

        # 4. Fallback if no valid sub-crops or if single item
        if not detections:
            logger.info(f"[VisionService] Single item or pile region; using full-image detection for '{anchor_class}'.")
            freshness = self.freshness_estimator.analyze_crop(image_rgb, anchor_class)
            exp_days = freshness["estimated_expiry_days"]
            det_status = self._status(exp_days, anchor_class)
            detections.append({
                "ingredient": anchor_class,
                "confidence": anchor_confidence,
                "box": {"x": 0, "y": 0, "w": int(img_w), "h": int(img_h)},
                "freshness_score": freshness["freshness_score"],
                "expiry_days": exp_days,
                "status": det_status,
            })

        # 5. Model Ranked Candidates: Deduplicated Full-Image Top-3 + High-Confidence Isolated Crop Predictions
        seen_classes = set()
        ranked_candidates = []

        # Anchor first
        seen_classes.add(anchor_class)
        ranked_candidates.append({
            "name": anchor_class,
            "confidence": anchor_confidence,
        })

        # High-confidence isolated crop predictions (e.g. Tomato when Potato is full-image anchor)
        for det in detections:
            dname = det["ingredient"]
            if dname not in seen_classes and det["confidence"] >= 0.55:
                seen_classes.add(dname)
                ranked_candidates.append({
                    "name": dname,
                    "confidence": float(det["confidence"]),
                })

        # Full-image top candidates (deduplicated)
        for cand in full_top_candidates:
            cname = cand["name"]
            if cname not in seen_classes:
                seen_classes.add(cname)
                ranked_candidates.append({
                    "name": cname,
                    "confidence": float(cand["confidence"]),
                })

        top_predictions = ranked_candidates[:top_k]
        primary_prediction = {
            "name": anchor_class,
            "confidence": anchor_confidence,
        }

        # 6. Aggregate Produce Inventory & Freshness Tracking
        ingredient_map: Dict[str, Dict[str, Any]] = {}
        distinct_classes = {d["ingredient"] for d in detections}

        # Pile aggregation ONLY applies when ALL detections belong to the SAME class
        # (e.g. dense bag of carrots with 6-8 carrots), NEVER when different items are present!
        if is_pile and len(distinct_classes) == 1:
            pile_count = min(12, max(len(detections), peak_count))
            min_exp = sorted(d["expiry_days"] for d in detections)[len(detections) // 2]
            status = self._status(min_exp, anchor_class)
            ingredient_map[anchor_class] = {
                "ingredient": anchor_class,
                "count": pile_count,
                "min_expiry_days": min_exp,
                "status": status,
            }
        else:
            # Multiple items or distinct separated classes (e.g. Tomato + Potato):
            for det in detections:
                ing = det["ingredient"]
                if ing not in ingredient_map:
                    ingredient_map[ing] = {
                        "ingredient": ing,
                        "count": 0,
                        "min_expiry_days": det["expiry_days"],
                        "status": det["status"],
                    }
                ingredient_map[ing]["count"] += 1
                ingredient_map[ing].setdefault("_exp", []).append(det["expiry_days"])

            for ing, info in ingredient_map.items():
                # median, not min: one shadowed crop must not mark every item of that class "Use First"
                exps = sorted(info.pop("_exp", [info["min_expiry_days"]]))
                info["min_expiry_days"] = exps[len(exps) // 2]
                info["status"] = self._status(info["min_expiry_days"], ing)

        inventory = list(ingredient_map.values())
        total_items_detected = sum(item["count"] for item in inventory)

        # 6b. Vision-LLM override: the CNN misreads ordinary photos, so the LLM decides WHICH ingredients
        # are present. CNN-derived boxes, counts and freshness are kept only for classes the LLM confirms.
        if isinstance(image_input, bytes):
            raw_bytes = image_input
        else:
            _buf = io.BytesIO()
            rgb_img.save(_buf, format="JPEG", quality=90)
            raw_bytes = _buf.getvalue()
        vlm_items = identify_ingredients(raw_bytes, self.class_names)
        if vlm_items:
            cnn_inv = {i["ingredient"]: i for i in inventory}
            cnn_conf = {c["name"]: float(c["confidence"]) for c in full_top_candidates}
            for d in detections:
                cnn_conf[d["ingredient"]] = max(cnn_conf.get(d["ingredient"], 0.0), float(d["confidence"]))
            vlm_names = [i["name"] for i in vlm_items]

            inventory = []
            for it in vlm_items:
                name = it["name"]
                count = it["count"]  # focused, per-item count from the vision LLM
                if name in cnn_inv:
                    exp = cnn_inv[name]["min_expiry_days"]
                else:
                    exp = self.freshness_estimator.get_base_shelf_life(name)
                inventory.append({
                    "ingredient": name,
                    "count": count,
                    "min_expiry_days": exp,
                    "status": self._status(exp, name),
                })
            total_items_detected = sum(i["count"] for i in inventory)
            detections = []  # CNN boxes are unreliable here and would contradict the verified counts; show the plain photo

            top_predictions = [
                {"name": n, "confidence": round(max(cnn_conf.get(n, 0.0), 0.85), 4)} for n in vlm_names[:top_k]
            ]
            primary_prediction = dict(top_predictions[0])

        # 7. Generate annotated visualization image
        annotated_rgb = self.segmenter.annotate_image(image_rgb, detections)
        annotated_b64 = self.segmenter.encode_base64_jpeg(annotated_rgb)

        logger.info(
            f"[VisionService] Completed multi-item detection: {len(detections)} instances, "
            f"{len(inventory)} unique produce classes (Total count: {total_items_detected})."
        )

        return {
            "prediction": primary_prediction,
            "top_predictions": top_predictions,
            "inventory": inventory,
            "detections": detections,
            "annotated_image": annotated_b64,
            "total_items_detected": total_items_detected,
        }


# Singleton instance container
_vision_service_instance: Optional[VisionService] = None


def get_vision_service() -> VisionService:
    """
    Returns the single global VisionService instance.
    Initializes it if not yet loaded.
    """
    global _vision_service_instance
    if _vision_service_instance is None:
        _vision_service_instance = VisionService()
    return _vision_service_instance


# Convenience proxy / default instance
vision_service = get_vision_service()

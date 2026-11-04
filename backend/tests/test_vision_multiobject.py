"""
Test suite for DishGenieAI custom OpenCV Multi-Item Segmentation, Counting,
Visual Freshness Grading, Expiry Estimation, and Qwen2.5 Prompt Injection.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.app.schemas.recipe import InventoryItem, RecipePreferences, RecipeRequest
from backend.app.services.freshness_estimator import (
    BASE_SHELF_LIFE_DAYS,
    FreshnessAndExpiryEstimator,
    get_base_shelf_life,
)
from backend.app.services.item_segmenter import (
    ItemSegmenter,
    merge_boxes,
    calculate_iou,
)
from backend.app.services.recipe_service import RecipeService
from backend.app.services.vision_service import DEFAULT_CLASSES_PATH, VisionService


class TestItemSegmenter(unittest.TestCase):
    def setUp(self):
        self.segmenter = ItemSegmenter(
            min_area_ratio=0.01,
            max_area_ratio=0.95,
            min_dim_ratio=0.05,
        )

    def test_single_item_fallback(self):
        # A uniform blank image with no distinct edges/contours
        blank_img = np.full((300, 300, 3), 240, dtype=np.uint8)
        boxes = self.segmenter.segment(blank_img)
        # Should fall back to the entire image
        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0], (0, 0, 300, 300))

    def test_multi_item_segmentation(self):
        # Create a synthetic image with 3 distinct items on a clean background
        img = np.full((400, 500, 3), 245, dtype=np.uint8)
        # Item 1: dark green circle
        cv2.circle(img, (100, 150), 45, (30, 140, 40), -1)
        # Item 2: red rectangle
        cv2.rectangle(img, (240, 100), (330, 200), (20, 30, 200), -1)
        # Item 3: orange circle
        cv2.circle(img, (400, 280), 50, (10, 120, 220), -1)

        boxes = self.segmenter.segment(img)
        self.assertGreaterEqual(len(boxes), 3)

    def test_strict_box_filtering_and_containment(self):
        default_seg = ItemSegmenter(min_area_ratio=0.06, min_dim_ratio=0.15)
        img_shape = (500, 500)  # total area = 250,000; min_area = 15,000; min_dim = 75

        # 1. Tiny shadow/texture box: area = 40*40 = 1,600 (< 15,000)
        tiny_box = (10, 10, 40, 40)
        filtered = default_seg.filter_candidate_boxes([tiny_box], img_shape)
        self.assertEqual(len(filtered), 0)

        # 2. Large valid box: 150 x 150 (area = 22,500 > 15,000, dims > 75)
        large_box = (50, 50, 150, 150)
        # 3. Internal shadow box inside large_box: (70, 70, 80, 80) (> 70% contained)
        internal_box = (70, 70, 80, 80)
        filtered_contain = default_seg.filter_candidate_boxes([large_box, internal_box], img_shape)
        self.assertEqual(len(filtered_contain), 1)
        self.assertEqual(filtered_contain[0], large_box)

    def test_square_context_crop(self):
        img = np.full((400, 400, 3), 180, dtype=np.uint8)
        # Bounding box of vegetable: (100, 150, 80, 50)
        box = (100, 150, 80, 50)
        crop = self.segmenter.get_square_context_crop(img, box, margin_ratio=0.25)
        h, w = crop.shape[:2]
        # Max dim = 80 -> side = 80 * 1.5 = 120
        self.assertEqual(h, 120)
        self.assertEqual(w, 120)

    def test_iou_box_merging(self):
        # Two highly overlapping boxes
        b1 = (50, 50, 100, 100)
        b2 = (55, 55, 95, 95)
        merged = merge_boxes([b1, b2], iou_threshold=0.35)
        self.assertEqual(len(merged), 1)

    def test_annotation_generation(self):
        img = np.full((200, 200, 3), 200, dtype=np.uint8)
        detections = [
            {
                "box": {"x": 10, "y": 10, "w": 80, "h": 80},
                "ingredient": "tomato",
                "confidence": 0.92,
                "expiry_days": 4,
                "status": "Medium",
            }
        ]
        annotated = self.segmenter.annotate_image(img, detections)
        self.assertEqual(annotated.shape, img.shape)
        b64 = self.segmenter.encode_base64_jpeg(annotated)
        self.assertTrue(b64.startswith("data:image/jpeg;base64,"))
        self.assertGreater(len(b64), 100)

    def test_watershed_touching_items(self):
        # Create synthetic image with 2 touching circles on light background
        img = np.full((350, 500, 3), 245, dtype=np.uint8)
        # Circle 1 (Tomato 1): Center (170, 175), radius 40
        cv2.circle(img, (170, 175), 40, (30, 30, 210), -1)
        # Circle 2 (Tomato 2): Center (240, 175), radius 40 - touching circle 1 (distance 70 < 2*40=80)
        cv2.circle(img, (240, 175), 40, (30, 30, 210), -1)

        boxes = self.segmenter.segment(img)
        # Distance transform + Watershed must cleanly split the 2 touching items into >= 2 boxes
        self.assertGreaterEqual(len(boxes), 2)

    def test_blob_splitting_geometry(self):
        from backend.app.services.item_segmenter import split_elongated_or_large_box
        # Box with aspect ratio 2.4 (side by side items)
        wide_box = (10, 10, 240, 100)
        splits = split_elongated_or_large_box(wide_box, img_shape=(400, 400, 3))
        self.assertEqual(len(splits), 2)
        # Sub-boxes should split along width (horizontal)
        self.assertLess(splits[0][2], wide_box[2])
        self.assertLess(splits[1][2], wide_box[2])


class TestFreshnessAndExpiryEstimator(unittest.TestCase):
    def setUp(self):
        self.estimator = FreshnessAndExpiryEstimator()

    def test_all_247_classes_mapped(self):
        # Verify all classes in dishgenie_classes.json have valid base shelf life
        if DEFAULT_CLASSES_PATH.exists():
            with open(DEFAULT_CLASSES_PATH, "r", encoding="utf-8") as f:
                classes = json.load(f)
            for cls in classes:
                days = get_base_shelf_life(cls)
                self.assertIsInstance(days, int)
                self.assertGreaterEqual(days, 1)

    def test_fresh_vs_stale_scoring(self):
        # Create a fresh vibrant green patch
        fresh_crop = np.zeros((100, 100, 3), dtype=np.uint8)
        fresh_crop[:, :] = (40, 200, 30)  # RGB vibrant green

        res_fresh = self.estimator.analyze_crop(fresh_crop, "spinach")
        self.assertGreaterEqual(res_fresh["freshness_score"], 0.70)
        self.assertIn(res_fresh["status"], ["Fresh", "Medium"])

        # Create a decayed / brown spotted patch (spinach with necrotic decay in center ROI)
        decayed_crop = np.full((100, 100, 3), (40, 200, 30), dtype=np.uint8)
        decayed_crop[30:70, 30:70] = (50, 40, 25)  # Dark brown necrotic spot

        res_decayed = self.estimator.analyze_crop(decayed_crop, "spinach")
        self.assertLess(res_decayed["freshness_score"], res_fresh["freshness_score"])
        self.assertLessEqual(res_decayed["estimated_expiry_days"], res_fresh["estimated_expiry_days"])

    def test_relative_uniformity_potato_and_onion(self):
        # Naturally brown item (Potato): RGB ~ (160, 120, 80)
        potato_crop = np.full((100, 100, 3), (160, 120, 80), dtype=np.uint8)
        res_potato = self.estimator.analyze_crop(potato_crop, "potato")
        # Relative surface uniformity should not penalize natural brown baseline color
        self.assertGreaterEqual(res_potato["freshness_score"], 0.80)
        self.assertEqual(res_potato["status"], "Fresh")

        # Naturally white item (Garlic): RGB ~ (230, 225, 215)
        garlic_crop = np.full((100, 100, 3), (230, 225, 215), dtype=np.uint8)
        res_garlic = self.estimator.analyze_crop(garlic_crop, "garlic")
        self.assertGreaterEqual(res_garlic["freshness_score"], 0.80)
        self.assertEqual(res_garlic["status"], "Fresh")

    def test_specular_and_shadow_filtering(self):
        # Base healthy tomato red (200, 40, 35) with specular highlights and edge shadows
        crop = np.full((120, 120, 3), (200, 40, 35), dtype=np.uint8)
        # Specular glares: V > 240, S < 30 (pure white glare)
        crop[50:60, 50:60] = (255, 255, 255)
        # Deep cast shadow edge: V < 25
        crop[0:15, :] = (15, 10, 10)

        res = self.estimator.analyze_crop(crop, "tomato")
        # With specular and shadow filtering, the center surface remains healthy red
        self.assertGreaterEqual(res["freshness_score"], 0.75)
        self.assertIn(res["status"], ["Fresh", "Medium"])

    def test_use_first_flag_threshold(self):
        # Severe decay on cilantro (base days = 5)
        stale_crop = np.full((100, 100, 3), (40, 180, 40), dtype=np.uint8)
        stale_crop[25:75, 25:75] = (45, 35, 20)  # Heavy necrotic decay covering center ROI
        res = self.estimator.analyze_crop(stale_crop, "cilantro")
        self.assertLessEqual(res["estimated_expiry_days"], 3)
        self.assertEqual(res["status"], "Use First")


class TestVisionServiceMultiObjectInference(unittest.TestCase):
    def test_aspect_ratio_padded_preprocessing(self):
        service = VisionService()
        # Elongated image (e.g. carrot or cucumber: 60 x 220)
        elongated_img = np.full((60, 220, 3), 150, dtype=np.uint8)
        tensor = service.preprocess_image(elongated_img)
        self.assertEqual(tensor.shape, (1, 224, 224, 3))
        self.assertTrue(np.all(tensor >= 0.0) and np.all(tensor <= 255.0))

    def test_multi_crop_inventory_aggregation(self):
        service = VisionService()
        service.class_names = ["tomato", "potato", "onion", "carrot"]
        service.segmenter = ItemSegmenter(min_area_ratio=0.01, min_dim_ratio=0.05)

        # Mock model instance
        mock_model = MagicMock()
        service.model = mock_model

        tomato_name = "tomato"
        potato_name = "potato"

        # Valid probability distributions that sum to 1.0
        prob_tomato = np.array([[0.94, 0.02, 0.02, 0.02]], dtype=np.float32)
        prob_potato = np.array([[0.02, 0.94, 0.02, 0.02]], dtype=np.float32)

        # 1st call is Full-Image Anchor (tomato), 2nd and 3rd are tomato crops, 4th is potato crop
        call_count = {"count": 0}

        def mock_predict_fn(batch, verbose=0):
            call_count["count"] += 1
            if call_count["count"] <= 3:
                return prob_tomato
            return prob_potato

        mock_model.predict.side_effect = mock_predict_fn

        # Synthetic multi-item image with 3 distinct shapes that pass contour detection
        img = np.full((400, 500, 3), 245, dtype=np.uint8)
        cv2.circle(img, (100, 150), 45, (30, 140, 40), -1)
        cv2.rectangle(img, (240, 100), (330, 200), (20, 30, 200), -1)
        cv2.circle(img, (400, 280), 50, (10, 120, 220), -1)

        result = service.predict(img)

        # Check that result contains inventory and detections
        self.assertIn("inventory", result)
        self.assertIn("detections", result)
        self.assertIn("annotated_image", result)

        inventory_map = {item["ingredient"]: item for item in result["inventory"]}
        self.assertIn(tomato_name, inventory_map)
        self.assertIn(potato_name, inventory_map)
        self.assertEqual(inventory_map[tomato_name]["count"], 2)
        self.assertEqual(inventory_map[potato_name]["count"], 1)
        self.assertEqual(result["total_items_detected"], 3)

        # Verify Full-Image Top-1 Anchor Prediction
        self.assertEqual(result["prediction"]["name"], tomato_name)

        # Verify candidate list has strictly unique class names (no duplicates)
        candidate_names = [c["name"] for c in result["top_predictions"]]
        self.assertEqual(len(candidate_names), len(set(candidate_names)))

    def test_connected_pile_consistency_gate(self):
        service = VisionService()
        service.class_names = ["carrot", "banana", "capsicum", "potato"]
        service.segmenter = ItemSegmenter(min_area_ratio=0.01, min_dim_ratio=0.05)

        mock_model = MagicMock()
        service.model = mock_model

        prob_carrot = np.array([[0.95, 0.02, 0.02, 0.01]], dtype=np.float32)
        prob_banana = np.array([[0.01, 0.96, 0.02, 0.01]], dtype=np.float32)

        call_count = {"count": 0}

        def mock_predict_fn(batch, verbose=0):
            call_count["count"] += 1
            # Full image is carrot; sub-crops simulate hallucinated banana on carrot texture
            if call_count["count"] == 1:
                return prob_carrot
            return prob_banana

        mock_model.predict.side_effect = mock_predict_fn

        # Connected pile image covering > 40% of the area
        pile_img = np.full((400, 400, 3), 245, dtype=np.uint8)
        # Draw large connected carrot pile covering > 45% of image
        cv2.rectangle(pile_img, (50, 50), (350, 350), (30, 100, 220), -1)

        result = service.predict(pile_img)

        # Consistency gate must override hallucinated banana with anchor class 'carrot'
        self.assertEqual(result["prediction"]["name"], "carrot")
        for item in result["inventory"]:
            self.assertEqual(item["ingredient"], "carrot")
            self.assertNotEqual(item["ingredient"], "banana")

    def test_tomato_potato_separated_items_not_overwritten(self):
        # Bug 1 verification: 1 Tomato and 1 Potato side-by-side must not merge into 2 Potatoes
        service = VisionService()
        service.class_names = ["potato", "tomato", "onion", "carrot"]
        service.segmenter = ItemSegmenter(min_area_ratio=0.01, min_dim_ratio=0.05)

        mock_model = MagicMock()
        service.model = mock_model

        # Full image anchor predicts Potato (e.g. 0.90)
        prob_potato = np.array([[0.90, 0.05, 0.03, 0.02]], dtype=np.float32)
        # Tomato crop predicts Tomato (0.92)
        prob_tomato = np.array([[0.03, 0.92, 0.03, 0.02]], dtype=np.float32)

        call_count = {"count": 0}

        def mock_predict_fn(batch, verbose=0):
            call_count["count"] += 1
            if call_count["count"] == 1:
                return prob_potato  # Full image anchor
            elif call_count["count"] == 2:
                return prob_tomato  # First crop is Tomato
            return prob_potato      # Second crop is Potato

        mock_model.predict.side_effect = mock_predict_fn

        # 2 distinct, spatially separated objects (Tomato on left, Potato on right)
        img = np.full((300, 500, 3), 245, dtype=np.uint8)
        # Tomato circle on left: center (120, 150), radius 60
        cv2.circle(img, (120, 150), 60, (30, 30, 220), -1)
        # Potato circle on right: center (380, 150), radius 60 (spatially separated, IoU = 0)
        cv2.circle(img, (380, 150), 60, (50, 120, 180), -1)

        result = service.predict(img)

        inventory_map = {item["ingredient"]: item for item in result["inventory"]}
        # Both must appear as distinct entries in the Inventory table
        self.assertIn("tomato", inventory_map)
        self.assertIn("potato", inventory_map)
        self.assertEqual(inventory_map["tomato"]["count"], 1)
        self.assertEqual(inventory_map["potato"]["count"], 1)
        self.assertEqual(result["total_items_detected"], 2)

        # Tomato must also appear in Model Ranked Candidates alongside Potato
        top_names = [c["name"] for c in result["top_predictions"]]
        self.assertIn("potato", top_names)
        self.assertIn("tomato", top_names)

    def test_bumpy_vegetable_no_overcounting(self):
        # Bug 2 verification: Bumpy texture (like bitter gourd) must not count 20+ units
        segmenter = ItemSegmenter(min_area_ratio=0.01, min_dim_ratio=0.05)
        # Synthetic single vegetable (200x200) with 20 textured bumpy ripple dots
        img = np.full((350, 350, 3), 245, dtype=np.uint8)
        # Draw central vegetable body
        cv2.ellipse(img, (175, 175), (90, 60), 0, 0, 360, (40, 140, 40), -1)
        # Add 20 high-contrast texture bumps inside the body
        for i in range(20):
            bx = 110 + (i % 5) * 30
            by = 130 + (i // 5) * 20
            cv2.circle(img, (bx, by), 6, (10, 80, 10), -1)

        fg_mask = segmenter.create_foreground_mask(img)
        boxes, raw_peaks = segmenter.segment_watershed(img, fg_mask)

        # Enforced 18% min peak distance and 21x21 Gaussian smoothing must suppress bumps
        # to <= 2 units (single vegetable), never 20+
        self.assertLessEqual(raw_peaks, 2)

    def test_tomato_stem_calyx_freshness_boost(self):
        # Bug 3 verification: Fresh bright red tomato with green stem/calyx must be graded Fresh (6-7d), not USE FIRST
        estimator = FreshnessAndExpiryEstimator()
        # Create bright fresh red tomato crop (120x120): HSV S ~ 190, V ~ 210
        tomato_crop = np.full((120, 120, 3), (210, 30, 25), dtype=np.uint8)
        # Add green calyx/stem at the top of the tomato: RGB (35, 175, 40) (Hue ~ 60, S ~ 180)
        tomato_crop[40:55, 45:75] = (35, 175, 40)

        res = estimator.analyze_crop(tomato_crop, "tomato")

        # Must exclude green stem, apply vibrancy boost, and score Fresh with >= 6 days expiry
        self.assertGreaterEqual(res["freshness_score"], 0.85)
        self.assertEqual(res["status"], "Fresh")
        self.assertGreaterEqual(res["estimated_expiry_days"], 6)

    def test_dense_pile_undercounting_fix(self):
        # Verification: A dense pile of touching items covering > 45% of image area
        # must count individual items inside the pile (2-12 items), never undercounting as 1.
        segmenter = ItemSegmenter()
        h, w = 400, 400
        pile_img = np.full((h, w, 3), 245, dtype=np.uint8)

        # Draw a dense homogeneous potato pile covering 64% of image area (> 45%)
        cv2.rectangle(pile_img, (40, 40), (360, 360), (60, 130, 185), -1)

        # Draw dark shadow valleys separating the touching potatoes
        for x in [140, 240]:
            cv2.line(pile_img, (x, 40), (x, 360), (30, 70, 110), 4)
        for y in [140, 240]:
            cv2.line(pile_img, (40, y), (360, y), (30, 70, 110), 4)

        boxes, pile_info = segmenter.segment_with_pile_info(pile_img)

        self.assertTrue(pile_info["is_pile"])
        self.assertGreaterEqual(len(boxes), 2)
        self.assertLessEqual(len(boxes), 12)
        self.assertEqual(pile_info["peak_count"], len(boxes))

    def test_bounding_box_label_use_first_only_on_expiry_le_3(self):
        # Verification: [USE FIRST] is ONLY appended if expiry_days <= 3.
        # Colors: Green for >7d, Amber/Yellow for 4-7d, Red for <=3d.
        segmenter = ItemSegmenter()
        img = np.full((300, 300, 3), 255, dtype=np.uint8)

        detections = [
            # 1. Potato (10d) -> Fresh, Green, NO [USE FIRST]
            {"box": {"x": 10, "y": 10, "w": 80, "h": 80}, "ingredient": "potato", "expiry_days": 10, "status": "Fresh"},
            # 2. Carrot (6d) -> Medium, Amber/Yellow, NO [USE FIRST]
            {"box": {"x": 100, "y": 10, "w": 80, "h": 80}, "ingredient": "carrot", "expiry_days": 6, "status": "Medium"},
            # 3. Spinach (2d) -> Use First, Red/Pink, WITH [USE FIRST]
            {"box": {"x": 190, "y": 10, "w": 80, "h": 80}, "ingredient": "spinach", "expiry_days": 2, "status": "Use First"},
        ]

        annotated = segmenter.annotate_image(img, detections)
        self.assertIsNotNone(annotated)

        # Check color of tag backgrounds
        # For Potato (10d), color is Emerald Green (5, 150, 105)
        self.assertTrue(np.any((annotated[:, :, 0] == 5) & (annotated[:, :, 1] == 150) & (annotated[:, :, 2] == 105)))
        # For Carrot (6d), color is Amber (217, 119, 6)
        self.assertTrue(np.any((annotated[:, :, 0] == 217) & (annotated[:, :, 1] == 119) & (annotated[:, :, 2] == 6)))
        # For Spinach (2d), color is Rose/Red (225, 29, 72)
        self.assertTrue(np.any((annotated[:, :, 0] == 225) & (annotated[:, :, 1] == 29) & (annotated[:, :, 2] == 72)))

    def test_fresh_tomato_rgb_and_bgr_freshness_score(self):
        # Verification: Shiny fresh tomato in both RGB and BGR evaluates to 6-7d, never 3d USE FIRST
        estimator = FreshnessAndExpiryEstimator()

        # RGB: Red channel is 220, Green 35, Blue 30
        rgb_tomato = np.full((100, 100, 3), (220, 35, 30), dtype=np.uint8)
        res_rgb = estimator.analyze_crop(rgb_tomato, "tomato", is_bgr=False)
        self.assertGreaterEqual(res_rgb["freshness_score"], 0.80)
        self.assertIn(res_rgb["estimated_expiry_days"], [6, 7])
        self.assertNotEqual(res_rgb["status"], "Use First")

        # BGR: Blue channel is 30, Green 35, Red is 220
        bgr_tomato = cv2.cvtColor(rgb_tomato, cv2.COLOR_RGB2BGR)
        res_bgr_explicit = estimator.analyze_crop(bgr_tomato, "tomato", is_bgr=True)
        self.assertGreaterEqual(res_bgr_explicit["freshness_score"], 0.80)
        self.assertIn(res_bgr_explicit["estimated_expiry_days"], [6, 7])
        self.assertNotEqual(res_bgr_explicit["status"], "Use First")

        # BGR auto-detected:
        res_bgr_auto = estimator.analyze_crop(bgr_tomato, "tomato")
        self.assertGreaterEqual(res_bgr_auto["freshness_score"], 0.80)
        self.assertIn(res_bgr_auto["estimated_expiry_days"], [6, 7])
        self.assertNotEqual(res_bgr_auto["status"], "Use First")

    def test_two_stage_hybrid_localization_and_custom_cnn_classification(self):
        # Verification of Two-Stage Hybrid Pipeline:
        # Stage 1 proposes boxes as a class-agnostic RPN; Stage 2 classifies every box using custom 247-class CNN.
        service = VisionService()
        service.class_names = ["bitter_gourd", "potato", "tomato", "capsicum"]

        mock_segmenter = ItemSegmenter()
        # Mock Stage 1 YOLO RPN proposals for a dense pile of 4 overlapping bitter gourds
        proposed_boxes = [
            (50, 50, 120, 100),
            (140, 60, 110, 110),
            (60, 140, 120, 100),
            (150, 150, 110, 110),
        ]
        mock_segmenter.propose_regions_yolo = MagicMock(return_value=proposed_boxes)
        service.segmenter = mock_segmenter

        mock_model = MagicMock()
        service.model = mock_model

        # Full image anchor is bitter_gourd (0.92)
        prob_bg = np.array([[0.92, 0.03, 0.03, 0.02]], dtype=np.float32)
        # Conflicted crop prediction (e.g. low-confidence capsicum 0.40)
        prob_capsicum = np.array([[0.20, 0.10, 0.10, 0.40]], dtype=np.float32)

        call_count = {"count": 0}

        def mock_predict_fn(batch, verbose=0):
            call_count["count"] += 1
            if call_count["count"] == 1:
                return prob_bg
            return prob_capsicum

        mock_model.predict.side_effect = mock_predict_fn

        dummy_img = np.full((300, 300, 3), 200, dtype=np.uint8)
        result = service.predict(dummy_img)

        # Stage 1 proposed 4 items, and Stage 2 snapped the conflicted/low-conf crops to bitter_gourd
        self.assertEqual(result["total_items_detected"], 4)
        self.assertEqual(len(result["inventory"]), 1)
        self.assertEqual(result["inventory"][0]["ingredient"], "bitter_gourd")
        self.assertEqual(result["inventory"][0]["count"], 4)
        self.assertEqual(len(result["detections"]), 4)


class TestRecipePromptInjection(unittest.TestCase):
    def test_prompt_includes_inventory_and_use_first(self):
        service = RecipeService(use_llm=False)

        req = RecipeRequest(
            ingredients=["tomato", "potato", "spinach"],
            inventory=[
                InventoryItem(
                    ingredient="spinach",
                    count=2,
                    min_expiry_days=2,
                    status="Use First",
                ),
                InventoryItem(
                    ingredient="tomato",
                    count=3,
                    min_expiry_days=6,
                    status="Fresh",
                ),
            ],
            preferences=RecipePreferences(
                diet="Vegetarian",
                cuisine="Indian",
                cooking_time=30,
                difficulty="Easy",
                servings=2,
            ),
        )

        messages = service.build_prompt_and_messages(
            ingredients=req.ingredients,
            preferences=req.preferences,
            candidates=[],
            inventory=req.inventory,
        )

        system_content = messages[0]["content"]
        user_content = messages[1]["content"]

        # Verify prompt injection
        self.assertIn("Available Inventory", user_content)
        self.assertIn("Spinach", user_content)
        self.assertIn("USE FIRST", user_content)
        self.assertIn("2 item(s)", user_content)
        self.assertIn("Tomato", user_content)
        self.assertIn("FOOD WASTE PREVENTION", system_content)
        self.assertIn("SHOPPING LIST SHORTFALL", system_content)


if __name__ == "__main__":
    unittest.main()

"""
Open-vocabulary ingredient recogniser backed by a local Ollama vision model (default gemma3:4b).

The 247-class CNN only knows a fixed (largely East-Asian) produce list and misreads ordinary photos,
so this recogniser decides WHICH ingredients are present; the CNN pipeline still supplies boxes/counts.
Returns [] on any failure so the caller can fall back to the CNN alone.
"""
import base64
import io
import json
import logging
import os
import re
from typing import Dict, List

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
VISION_MODEL = os.getenv("VISION_LLM_MODEL", "gemma3:4b")

PROMPT = (
    "You are a kitchen inventory scanner. List every distinct raw food ingredient (vegetable, fruit, herb, "
    "mushroom, nut, spice) that is clearly visible in this photo, with an estimated count of whole pieces of each "
    "(count a bunch or pile as roughly how many pieces you can see). Only list items you are highly confident "
    "about; when unsure, leave the item out. Use plain singular common names such as "
    '"potato", "tomato", "bell pepper", "carrot", "eggplant". Do NOT list plates, containers, leaves of the '
    "plant, hands, water or background objects. Do NOT guess items that are not visible. "
    'Answer ONLY with JSON: {"items":[{"name":"potato","count":3}]}'
)

# common English / regional names -> CNN class names used across the app
ALIASES: Dict[str, str] = {
    "bell_pepper": "capsicum", "sweet_pepper": "capsicum", "green_pepper": "capsicum", "red_pepper": "capsicum",
    "yellow_pepper": "capsicum", "green_bell_pepper": "capsicum", "red_bell_pepper": "capsicum",
    "chili": "pepper", "chilli": "pepper", "chili_pepper": "pepper", "green_chili": "pepper", "green_chilli": "pepper",
    "hot_pepper": "pepper", "red_chili": "pepper", "jalapeno": "pepper",
    "eggplant": "brinjal", "aubergine": "brinjal",
    "cilantro": "coriander", "coriander_leaves": "coriander",
    "spring_onion": "scallion", "green_onion": "scallion", "red_onion": "onion", "white_onion": "onion",
    "yellow_onion": "onion", "courgette": "zucchini", "kiwi": "kiwi_fruit", "kiwifruit": "kiwi_fruit",
    "okra": "okra", "ladyfinger": "okra", "lady's_finger": "okra", "beet": "beetroot", "beets": "beetroot",
    "red_potato": "potato", "sweet_potatoes": "sweet_potato",
    "green_bean": "bean", "green_beans": "bean", "french_bean": "bean", "string_bean": "bean",
    "bitter_melon": "bitter_gourd", "bitter_gourd": "bitter_gourd", "karela": "bitter_gourd",
    "bottle_gourd": "bottle_gourd", "lauki": "bottle_gourd", "radish": "radish", "daikon": "radish",
    "peas": "pea", "green_pea": "pea", "green_peas": "pea", "corn_on_the_cob": "corn", "sweetcorn": "corn",
    "mushrooms": "mushroom", "white_mushroom": "agaricus_bisporus", "button_mushroom": "agaricus_bisporus",
    "collard_greens": "spinach", "garlic_clove": "garlic", "garlic_bulb": "garlic",
    "plantain": "banana", "raw_banana": "banana", "lemons": "lemon", "limes": "lime",
}

# non-ingredients the model sometimes emits anyway
JUNK = {
    "leaf", "leaves", "stem", "stems", "water", "plate", "bowl", "basket", "background", "table", "hand",
    "container", "bag", "box", "tray", "knife", "cutting_board", "vegetable", "vegetables", "fruit", "fruits",
    "produce", "food", "plant", "tree", "wood", "cloth", "paper", "...", "",
}

MAX_ITEMS = 8
MAX_VERIFY = 6
MAX_COUNT = 12

# CNN class name -> natural phrase for the focused counting question
SPOKEN = {"capsicum": "bell pepper", "brinjal": "eggplant", "pepper": "chili pepper", "bitter_gourd": "bitter melon",
          "agaricus_bisporus": "mushroom", "scallion": "spring onion", "kiwi_fruit": "kiwi"}


def _canonical(name: str, known: set) -> str:
    n = re.sub(r"[^a-z' ]", "", str(name).lower()).strip().replace(" ", "_")
    if n in ALIASES:
        return ALIASES[n]
    for cand in (n, n[:-2] if n.endswith("es") else None, n[:-1] if n.endswith("s") else None):
        if cand and cand in ALIASES:
            return ALIASES[cand]
        if cand and cand in known:
            return cand
    return n


def _prepare_image(image_bytes: bytes, max_side: int = 768) -> str:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()


def parse_items(raw: str, known: set) -> List[Dict]:
    """Parse model text (JSON, possibly fenced or a bare list) into merged [{'name','count'}]."""
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        data = json.loads(raw)
        items = data.get("items", []) if isinstance(data, dict) else data
    except Exception:
        # truncated/malformed JSON: salvage every complete {"name":..,"count":..} object
        items = [
            {"name": n, "count": c}
            for n, c in re.findall(r'"name"\s*:\s*"([^"]+)"\s*,\s*"count"\s*:\s*(\d+)', raw)
        ]
    merged: Dict[str, int] = {}
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or not it.get("name"):
            continue
        name = _canonical(it["name"], known)
        if name in JUNK or len(name) < 3:
            continue
        try:
            count = max(1, int(it.get("count", 1)))
        except (TypeError, ValueError):
            count = 1
        merged[name] = merged.get(name, 0) + count
    return [{"name": n, "count": c} for n, c in list(merged.items())[:MAX_ITEMS]]


def _chat(img_b64: str, prompt: str, num_predict: int) -> str:
    r = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": VISION_MODEL,
            "stream": False,
            "keep_alive": "30m",
            "messages": [{"role": "user", "content": prompt, "images": [img_b64]}],
            "options": {"temperature": 0, "num_ctx": 4096, "num_predict": num_predict},
        },
        timeout=float(os.getenv("VISION_LLM_TIMEOUT", "120")),
    )
    r.raise_for_status()
    return r.json()["message"]["content"]


def _verify(img_b64: str, name: str, listed: int) -> int:
    """Focused count of one candidate. 0 = not really there. Listing prompts hallucinate extras; this does not."""
    spoken = SPOKEN.get(name, name).replace("_", " ")
    q = (f"How many separate {spoken} pieces are clearly visible in this photo? "
         "Reply with just a number. Reply 0 if there are none or you are unsure.")
    try:
        m = re.search(r"\d+", _chat(img_b64, q, 8))
    except Exception as err:
        logger.warning(f"[VLMDetector] verify '{name}' failed, keeping listed count: {err}")
        return min(listed, MAX_COUNT)
    return min(int(m.group()), MAX_COUNT) if m else min(listed, MAX_COUNT)


def identify_ingredients(image_bytes: bytes, known_classes: List[str]) -> List[Dict]:
    """Returns verified [{'name','count'}] from the vision LLM, or [] if disabled/unavailable/unparseable."""
    if os.getenv("VISION_LLM_ENABLED", "true").strip().lower() not in ("true", "1", "yes"):
        return []
    try:
        img_b64 = _prepare_image(image_bytes)
        listed = parse_items(_chat(img_b64, PROMPT, 400), set(known_classes))
        items = []
        for it in listed[:MAX_VERIFY]:
            n = _verify(img_b64, it["name"], it["count"])
            if n > 0:
                items.append({"name": it["name"], "count": n})
        logger.info(f"[VLMDetector] {VISION_MODEL} listed {listed} -> verified {items}")
        return items
    except Exception as err:
        logger.warning(f"[VLMDetector] vision LLM unavailable, using CNN only: {err}")
        return []

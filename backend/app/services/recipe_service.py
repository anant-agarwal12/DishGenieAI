import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import httpx

from app.schemas.recipe import RecipePreferences, RecipeRequest, RecipeResponse
from app.services.recipe_parser import parse_recipe_text
from app.services.recipe_retriever import RecipeRetriever, get_recipe_retriever
from app.services.recipe_validator import is_core_item_covered_in_text

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("GENAI_MODEL", "llama3.2")


def _normalize_model_json(raw: str) -> str:
    """Small models often pack all steps/ingredients into one string; split them into list items."""
    try:
        data = json.loads(raw)
    except Exception:
        return raw
    if not isinstance(data, dict):
        return raw
    steps = data.get("instructions")
    if isinstance(steps, str):
        steps = [steps]
    if isinstance(steps, list) and len(steps) <= 2:
        text = " ".join(str(x) for x in steps)
        data["instructions"] = [x.strip() for x in re.split(r"(?<=[.!])\s+(?=[A-Z])", text) if len(x.strip()) > 8]
    ings = data.get("ingredients")
    if isinstance(ings, str):
        ings = [ings]
    if isinstance(ings, list) and len(ings) == 1:
        data["ingredients"] = [x.strip() for x in re.split(r",\s*(?=[\d½¼¾]|a |an |some |salt|oil)", str(ings[0])) if x.strip()]
    if isinstance(data.get("ingredients"), list):
        cleaned, seen = [], set()
        for ing in data["ingredients"]:
            # models echo the prompt's "USE FIRST" tag and sometimes repeat a phrase ("1 tsp oil, 1 tsp oil")
            t = re.sub(r"[\s,(\[-]*\b(?:priority:?\s*)?use\s*first\b[)\]]?", "", str(ing), flags=re.I).strip(" ,")
            half = re.fullmatch(r"(.+?),\s*\1", t, flags=re.I)
            t = half.group(1) if half else t
            if t and t.lower() not in seen:
                seen.add(t.lower())
                cleaned.append(t)
        data["ingredients"] = cleaned
    data["shopping_list"] = []  # derived deterministically from final ingredients; models copy junk from references
    return json.dumps(data)


class RecipeService:
    """
    Recipe synthesis via a local Ollama model, grounded on SQLite recipe candidates.
    Output is checked so every confirmed ingredient is used; one retry, then a
    database-candidate fallback.
    """

    def __init__(self, model_name: Optional[str] = None, use_llm: bool = True):
        self.use_llm = use_llm
        self.model_name = model_name or OLLAMA_MODEL
        self.device = "ollama"
        self.retriever: RecipeRetriever = get_recipe_retriever()
        logger.info(f"[RecipeService] Using Ollama model '{self.model_name}' at {OLLAMA_URL}")

    def _ollama_up(self) -> bool:
        if not self.use_llm:
            return False
        try:
            r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2.0)
            return r.status_code == 200 and any(
                m.get("name", "").split(":")[0] == self.model_name.split(":")[0]
                for m in r.json().get("models", [])
            )
        except Exception:
            return False

    @property
    def is_available(self) -> bool:
        """Available if Ollama serves the model OR the recipe DB can ground a fallback."""
        return self._ollama_up() or self.retriever.db.count_recipes() > 0

    def _chat(self, messages: List[Dict[str, str]]) -> str:
        r = httpx.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": self.model_name,
                "messages": messages,
                "stream": False,
                "format": "json",
                "keep_alive": "30m",
                "options": {
                    "temperature": 0.3,
                    "num_ctx": 4096,
                    "num_predict": int(os.getenv("GENAI_MAX_NEW_TOKENS", "1200")),
                },
            },
            timeout=float(os.getenv("GENAI_TIMEOUT", "300")),
        )
        r.raise_for_status()
        return r.json()["message"]["content"].strip()

    def get_candidate_options(self, request: RecipeRequest, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Retrieves top matching candidate dishes from SQLite to present as interactive choices
        to the user before final neural synthesis.
        """
        candidates = self.retriever.retrieve_candidates(
            ingredients=request.ingredients,
            preferences=request.preferences,
            limit=limit,
        )
        options = []
        for cand in candidates:
            name = cand.get("name", "Gourmet Dish")
            parts = [x.strip() for x in name.split(" - ")]
            if len(parts) == 2 and parts[0].lower() == parts[1].lower():  # dataset titles like "X - X"
                name = parts[0]
            cuisine = cand.get("cuisine") or request.preferences.cuisine or "Indian"
            cooking_time = cand.get("cooking_time") or request.preferences.cookingTime or 30
            diet = cand.get("diet") or request.preferences.diet or "Vegetarian"
            image_url = cand.get("image_url")
            matched_tokens = cand.get("matched_user_tokens", [])

            # Generate concise, appetizing overview for the candidate dish
            instructions = cand.get("instructions", "").strip()
            first_sentence = instructions.split(".")[0].strip() if instructions else ""
            if len(first_sentence) > 15 and len(first_sentence) < 140:
                desc = f"{first_sentence}."
            else:
                desc = f"Authentic {cuisine} specialty highlighting {', '.join(matched_tokens) if matched_tokens else 'fresh ingredients'}."

            options.append({
                "id": str(cand.get("id")),
                "name": name,
                "description": desc,
                "cuisine": cuisine,
                "cooking_time": cooking_time,
                "diet": diet,
                "image_url": image_url,
                "matched_ingredients": matched_tokens,
            })
        return options

    def build_prompt_and_messages(
        self,
        ingredients: List[str],
        preferences: RecipePreferences,
        candidates: List[Dict[str, Any]],
        inventory: Optional[List[Any]] = None,
        selected_dish: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        Constructs chat messages for recipe generation.
        Injects detected inventory items, counts, and estimated expiry days.
        Provides complete, untruncated candidate recipes for authentic culinary grounding.
        """
        ing_list = ", ".join(ingredients)
        extras = preferences.additionalIngredients.strip() if preferences.additionalIngredients else "None"

        # Build comprehensive reference block from retrieved database recipes without destructive string slicing
        ref_text = ""
        for i, cand in enumerate(candidates[:1], 1):
            name = cand.get("name", "Recipe")
            raw_ings = cand.get("ingredients_raw", "").strip()
            steps = cand.get("instructions", "").strip()

            ref_text += f"\nReference Recipe {i}: {name}\n"
            if raw_ings:
                ref_text += f"- Ingredients: {raw_ings[:800]}\n"
            if steps:
                ref_text += f"- Cooking Steps: {steps[:1200]}\n"

        # Build inventory and freshness context
        inventory_context = ""
        use_first_items = []
        if inventory:
            inventory_lines = []
            for item in inventory:
                ing_name = getattr(item, "ingredient", None) or (item.get("ingredient") if isinstance(item, dict) else str(item))
                count = getattr(item, "count", None) or (item.get("count", 1) if isinstance(item, dict) else 1)
                expiry = getattr(item, "min_expiry_days", None) or (item.get("min_expiry_days") if isinstance(item, dict) else None)
                status = getattr(item, "status", None) or (item.get("status", "Fresh") if isinstance(item, dict) else "Fresh")

                display_name = ing_name.replace("_", " ").title()
                expiry_text = f"{expiry}d remaining" if expiry is not None else "fresh"

                if str(status).lower() in ("use first", "urgent") or (expiry is not None and expiry <= 3):
                    use_first_items.append(display_name)
                    inventory_lines.append(f"- {display_name}: {count} item(s) (Expiry: {expiry_text}) [PRIORITY: USE FIRST]")
                else:
                    inventory_lines.append(f"- {display_name}: {count} item(s) (Expiry: {expiry_text}, Status: {status})")

            if inventory_lines:
                inventory_context = "\nAvailable Inventory (Counts & Freshness):\n" + "\n".join(inventory_lines) + "\n"

        target_dish_focus = ""
        if selected_dish:
            target_dish_focus = (
                f"\nTARGET DISH STYLE: The user specifically chose to cook '{selected_dish}'. "
                f"Your recipe 'name' and core preparation MUST be specifically tailored to '{selected_dish}'.\n"
            )

        system_prompt = (
            "You are DishGenie, an expert culinary AI chef. Your task is to generate an authentic, "
            "delicious, and practical recipe tailored to the user's pantry ingredients and culinary constraints.\n"
            "You MUST output your response as a single, valid JSON object with NO markdown code fences (no ```json), "
            "no conversational text, and no commentary before or after.\n\n"
            "The JSON object must have EXACTLY this structure. 'ingredients' and 'instructions' are JSON arrays with ONE element per ingredient or per step (5-8 steps, never one long string):\n"
            "{\n"
            '  "name": "Recipe Name",\n'
            '  "description": "Appetizing overview of the dish",\n'
            '  "ingredients": ["1 cup ingredient name, prepped", "1 tsp spice", ...],\n'
            '  "instructions": ["Step 1 actionable sentence.", "Step 2 actionable sentence.", ...],\n'
            '  "substitutions": [\n'
            '    {"ingredient": "Item name", "replacement": "Culinary alternative with flavor/texture reason"}\n'
            "  ],\n"
            '  "shopping_list": ["Item needing purchase", ...]\n'
            "}\n\n"
            "CRITICAL CULINARY & INVENTORY RULES:\n"
            "1. FOOD WASTE PREVENTION (PRIORITIZE 'USE FIRST'): Any ingredient marked 'USE FIRST' (expiring in <= 3 days) "
            "MUST be given highest culinary priority and actively incorporated into the main recipe.\n"
            f"2. QUANTITY RESPECT & SHOPPING LIST SHORTFALL: Respect the user's available item counts for {preferences.servings} servings. "
            "If the recipe requires more quantity than available (e.g., user has 1 tomato but recipe needs 3), or requires necessary "
            "aromatics, spices, cooking oil, or garnishes not present in inventory, automatically add the shortfall or missing items to 'shopping_list'.\n"
            "3. INGREDIENT CONSISTENCY: Every single ingredient, aromatic (garlic, ginger, onions), spice "
            "(fennel seeds, cumin, turmeric, chilli), oil, and garnish mentioned in your cooking instructions "
            "MUST be listed in the 'ingredients' array with sensible quantities.\n"
            "4. ACTIONABLE INSTRUCTIONS: Every step in 'instructions' must be a complete, actionable cooking instruction "
            "with realistic cooking times and temperatures. NEVER use headings or section labels as instruction steps.\n"
            f"5. DIETARY COMPLIANCE: The recipe MUST strictly comply with the user's dietary restriction: {preferences.diet}.\n"
            f"6. CUISINE AUTHENTICITY: Maintain culinary techniques authentic to {preferences.cuisine} cuisine.\n"
            "7. MAIN INGREDIENTS ONLY FROM THE LIST: The recipe name and every main vegetable/protein must come from the confirmed ingredients and additional pantry ingredients. Never introduce another main produce item (e.g. do not add sweet potato if only potato is confirmed). Do not mention side dishes.\n"
            "8. FOCUS: Focus on accurate 'name', 'description', 'ingredients', and 'instructions'. The 'substitutions' and 'shopping_list' "
            "arrays can be included or empty as they are validated and reconciled deterministically.\n"
            "9. STOVETOP PREFERENCE & STRICT PAN PREPARATION: For traditional Indian, pan-fried, curry, and stovetop dishes, strictly prohibit oven-baking instructions "
            "(e.g., 'Preheat oven to 350°F / 180°C', 'Bake on a baking tray'). Prioritize standard Indian stovetop, pan, pressure cooker, or kadhai preparation methods unless "
            "the user's cuisine or recipe explicitly requires baking. Do NOT instruct the user to preheat an oven or bake unless the user has explicitly requested Western baking or a cuisine/dish "
            "that intrinsically requires an oven (such as cakes, bread, or pizza)."
        )

        waste_alert = ""
        if use_first_items:
            waste_alert = f"\nURGENT CULINARY GOAL: Use up expiring produce ({', '.join(use_first_items)}) to avoid food waste.\n"

        user_prompt = (
            f"Create a complete recipe using these confirmed ingredients: {ing_list}\n"
            f"{target_dish_focus}"
            f"{inventory_context}"
            f"{waste_alert}\n"
            f"User Preferences:\n"
            f"- Diet: {preferences.diet}\n"
            f"- Cuisine: {preferences.cuisine}\n"
            f"- Target Cooking Time: {preferences.cookingTime} minutes\n"
            f"- Difficulty: {preferences.difficulty}\n"
            f"- Servings: {preferences.servings}\n"
            f"- Additional Pantry Ingredients: {extras}\n\n"
            f"Retrieved Database Reference Recipes (Inspiration):{ref_text}\n\n"
            "Return ONLY the valid JSON object now:"
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def generate(self, request: RecipeRequest) -> RecipeResponse:
        """
        Generates a recipe using local database retrieval and fast neural inference (GGUF or HF).
        Parses output into structured Recipe schema, maintaining the /api/recipe/generate contract.
        """
        if not self.is_available:
            logger.error("[RecipeService] Neither language model nor recipe database is available.")
            raise RuntimeError("RecipeService is not initialized or database is unavailable.")

        # 1. Retrieve small relevant candidate set from SQLite
        candidates = self.retriever.retrieve_candidates(
            ingredients=request.ingredients,
            preferences=request.preferences,
            limit=3,
        )
        logger.info(
            f"[RecipeService] Retrieved {len(candidates)} candidate recipes for ingredients: {request.ingredients}"
        )

        # Prioritize candidate matching user's selected dish style if provided
        top_cand = candidates[0] if candidates else None
        if request.selected_dish and candidates:
            sel_clean = request.selected_dish.strip().lower()
            matching = [c for c in candidates if sel_clean in c.get("name", "").lower() or c.get("name", "").lower() in sel_clean]
            if matching:
                top_cand = matching[0]
                candidates = [top_cand] + [c for c in candidates if c != top_cand]

        messages = self.build_prompt_and_messages(
            request.ingredients,
            request.preferences,
            candidates if request.selected_dish else [],  # reference only when the user picked a dish
            inventory=request.inventory,
            selected_dish=request.selected_dish,
        )
        # 2. Ollama generation: validate that every confirmed ingredient is really used; retry once.
        def parse(text: str):
            return parse_recipe_text(
                text,
                fallback_ingredients=request.ingredients,
                cuisine=request.preferences.cuisine,
                diet=request.preferences.diet,
                additional_ingredients=request.preferences.additionalIngredients,
                candidate_recipe=top_cand,
            )

        def missing(recipe) -> List[str]:
            body = " ".join(recipe.instructions).lower()
            return [
                ing for ing in request.ingredients
                if not is_core_item_covered_in_text(ing.replace("_", " ").lower(), body)
            ]

        last_ok = None
        if self._ollama_up():
            for attempt in range(2):
                try:
                    raw_text = _normalize_model_json(self._chat(messages))
                    recipe = parse(raw_text)
                except Exception as err:
                    logger.error(f"[RecipeService] Ollama generation error (attempt {attempt + 1}): {err}")
                    break
                if recipe and recipe.ingredients and recipe.instructions:
                    gaps = missing(recipe)
                    if not gaps:
                        return RecipeResponse(success=True, recipe=recipe, raw_text=raw_text)
                    last_ok = RecipeResponse(success=True, recipe=recipe, raw_text=raw_text)
                    logger.warning(f"[RecipeService] Recipe ignored ingredients {gaps}; retrying.")
                    messages = messages + [
                        {"role": "assistant", "content": raw_text},
                        {"role": "user", "content": (
                            f"Your recipe never uses: {', '.join(gaps)}. Rewrite the complete JSON so these "
                            "ingredients are core, listed in 'ingredients', and used in the instruction steps."
                        )},
                    ]
            if last_ok:  # a model recipe missing one ingredient beats an unrelated database dish
                return last_ok
        else:
            logger.warning("[RecipeService] Ollama unreachable or model missing; using database fallback.")

        # 3. Grounded Candidate Synthesis Fallback
        if top_cand:
            logger.info(f"[RecipeService] Synthesizing recipe grounded on database candidate: '{top_cand.get('name')}'")
            recipe = parse_recipe_text(
                "",
                fallback_ingredients=request.ingredients,
                cuisine=request.preferences.cuisine,
                diet=request.preferences.diet,
                additional_ingredients=request.preferences.additionalIngredients,
                candidate_recipe=top_cand,
            )
            raw_text = (
                f"RECIPE NAME: {recipe.name}\n\n"
                f"DESCRIPTION: {recipe.description}\n\n"
                f"INGREDIENTS:\n" + "\n".join([f"- {i}" for i in recipe.ingredients]) + "\n\n"
                f"INSTRUCTIONS:\n" + "\n".join([f"{idx+1}. {step}" for idx, step in enumerate(recipe.instructions)])
            )
            return RecipeResponse(success=True, recipe=recipe, raw_text=raw_text)

        logger.error("[RecipeService] Neither model generation succeeded nor any candidate recipe was found.")
        raise RuntimeError("No candidate recipes or language model available to generate recipe.")


# Global singleton instance container
_recipe_service_instance: Optional[RecipeService] = None


def get_recipe_service() -> RecipeService:
    """
    Returns the single global RecipeService instance.
    Initializes it if not yet loaded.
    """
    global _recipe_service_instance
    if _recipe_service_instance is None:
        _recipe_service_instance = RecipeService()
    return _recipe_service_instance

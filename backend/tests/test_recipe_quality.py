"""
Automated unit and regression test suite for DishGenieAI Recipe Generation Quality and Data Consistency.

Covers:
1. Valid recipe with all six sections.
2. Papaya curry containing fennel seeds and garlic in instructions -> reconciled into ingredients & shopping list.
3. Instructions with missing ingredients reconciled cleanly without duplicates.
4. Markdown artifacts in headings and ingredient names stripped safely.
5. Incomplete instructions (e.g. 'Sprinkle salt over the') detected and filtered out.
6. Heading-only steps (e.g. 'For the Papaya Curry:**', 'Add Spices:**') filtered out of instructions.
7. Missing substitutions generated with diet-aware culinary rules.
8. Missing shopping-list data generated from recipe ingredients minus confirmed pantry.
9. Duplicate ingredients and unit consolidation.
10. Empty or malformed model output -> authentic database candidate fallback.
11. Invalid JSON returned by the model repaired or safely handled.
12. Database fallback when language model is unavailable preserves authentic database recipe data.
13. Strict dietary restrictions (e.g., Vegan diet avoids dairy substitutions and ingredients).
14. Optional ingredients and garnishes handling.
15. Legitimate short instructions preserved (e.g. 'Serve hot with steamed rice.').
"""

import json
import unittest
from pathlib import Path
import sys

# Ensure backend directory is in python path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.recipe import Recipe, RecipePreferences, RecipeRequest, RecipeResponse, Substitution
from app.services.recipe_parser import (
    create_recipe_from_database_candidate,
    parse_and_flatten_ingredients,
    parse_json_recipe,
    parse_recipe_text,
    repair_json_string,
    sanitize_text_field,
)
from app.services.recipe_validator import (
    clean_fraction_slashes,
    clean_instruction_step,
    deduplicate_and_consolidate_ingredients,
    extract_core_ingredient_key,
    generate_culinary_substitutions,
    generate_recipe_shopping_list,
    is_heading_or_label,
    is_incomplete_sentence,
    reconcile_ingredients_with_instructions,
    strip_markdown_formatting,
    validate_and_refine_recipe,
)


class TestRecipeQualityAndConsistency(unittest.TestCase):
    """Tests for recipe validation, formatting, and ingredient consistency."""

    def test_valid_recipe_with_all_six_sections(self):
        """Scenario 1: Valid recipe with all six sections parses cleanly without regressions."""
        raw_json = json.dumps({
            "name": "Paneer Butter Masala",
            "description": "Rich and creamy tomato-based cottage cheese curry.",
            "ingredients": ["200g Paneer cubes", "2 medium Tomatoes, pureed", "1 tbsp Butter", "1/2 tsp Garam masala"],
            "instructions": [
                "Melt butter in a pan over medium heat.",
                "Add tomato puree and cook until butter separates.",
                "Add paneer cubes and garam masala, simmering for 5 minutes.",
                "Serve hot with warm naan."
            ],
            "substitutions": [
                {"ingredient": "Paneer", "replacement": "Firm Tofu - provides identical texture for dairy-free preferences."}
            ],
            "shopping_list": ["Paneer", "Tomatoes", "Garam masala"]
        })

        recipe = parse_recipe_text(raw_json, fallback_ingredients=["paneer"])
        self.assertIsNotNone(recipe)
        self.assertEqual(recipe.name, "Paneer Butter Masala")
        self.assertTrue(len(recipe.description) > 0)
        self.assertEqual(len(recipe.instructions), 4)
        self.assertTrue(len(recipe.ingredients) >= 4)
        self.assertTrue(len(recipe.substitutions) >= 1)
        self.assertTrue(len(recipe.shopping_list) >= 1)

    def test_papaya_curry_fennel_and_garlic_reconciliation(self):
        """Scenario 2 & 3: Papaya curry containing fennel seeds and garlic in instructions is reconciled."""
        raw_json = json.dumps({
            "name": "Raw Papaya Curry",
            "description": "Fragrant raw papaya stewed with aromatic spices.",
            "ingredients": ["2 cups Raw papaya, peeled and cubed", "1/2 tsp Turmeric powder", "Salt to taste"],
            "instructions": [
                "Heat cooking oil in a pan and add fennel seeds until fragrant.",
                "Sauté crushed garlic until golden brown.",
                "Add cubed raw papaya, turmeric powder, and salt.",
                "Pour water, cover, and simmer for 15 minutes until tender.",
                "Garnish with fresh coriander and serve."
            ]
        })

        recipe = parse_recipe_text(raw_json, fallback_ingredients=["papaya"])
        self.assertIsNotNone(recipe)

        ing_text = " ".join(recipe.ingredients).lower()
        # Fennel seeds and garlic were in instructions, MUST be present in ingredients
        self.assertTrue("fennel" in ing_text or "saunf" in ing_text, "Fennel seeds must be reconciled into ingredients")
        self.assertTrue("garlic" in ing_text, "Garlic must be reconciled into ingredients")
        self.assertTrue("oil" in ing_text, "Cooking oil must be reconciled into ingredients")
        self.assertTrue("coriander" in ing_text, "Garnish coriander must be reconciled into ingredients")

        # Shopping list must also reflect the reconciled items
        shop_text = " ".join(recipe.shopping_list).lower()
        self.assertTrue("garlic" in shop_text or "fennel" in shop_text or "papaya" in shop_text)

    def test_markdown_artifacts_stripped(self):
        """Scenario 4: Stray markdown symbols like **, __, # are cleanly stripped from all sections."""
        raw_text = """
        RECIPE NAME: **Spiced Papaya Masala**
        DESCRIPTION: *A delightful __traditional__ curry.*
        INGREDIENTS:
        - **2 cups** raw papaya, cubed
        - __1 tsp__ cumin seeds
        - *1/2 tsp* turmeric
        INSTRUCTIONS:
        1. **Heat oil** in a heavy pan.
        2. Add **cumin seeds** and wait for them to splutter.
        3. Stir in __papaya cubes__ and simmer.
        """
        recipe = parse_recipe_text(raw_text, fallback_ingredients=["papaya"])
        self.assertIsNotNone(recipe)
        self.assertNotIn("**", recipe.name)
        self.assertNotIn("__", recipe.description)
        for ing in recipe.ingredients:
            self.assertNotIn("**", ing)
            self.assertNotIn("__", ing)
        for step in recipe.instructions:
            self.assertNotIn("**", step)
            self.assertNotIn("__", step)

    def test_incomplete_instruction_and_heading_rejection(self):
        """Scenario 5 & 6: Incomplete instructions and section labels/headings are detected and filtered."""
        # Heading tests
        self.assertTrue(is_heading_or_label("For the Papaya Curry:**"))
        self.assertTrue(is_heading_or_label("Prepare the Papaya and Tomato:**"))
        self.assertTrue(is_heading_or_label("Add Spices:"))
        self.assertTrue(is_heading_or_label("For Garnish:"))
        self.assertFalse(is_heading_or_label("Heat oil in a pan and add cumin seeds."))

        # Incomplete sentence tests
        self.assertTrue(is_incomplete_sentence("Sprinkle salt over the"))
        self.assertTrue(is_incomplete_sentence("Garnish with fresh"))
        self.assertTrue(is_incomplete_sentence("In a separate"))
        self.assertFalse(is_incomplete_sentence("Sprinkle salt over the curry and stir well."))

        raw_json = json.dumps({
            "name": "Papaya Sabzi",
            "description": "Tasty spiced papaya dish.",
            "ingredients": ["Raw papaya", "Salt", "Cumin seeds", "Oil"],
            "instructions": [
                "For the Papaya Curry:**",
                "Prepare the Papaya and Tomato:**",
                "Heat cooking oil in a pan and temper with cumin seeds.",
                "Add Spices:**",
                "Sprinkle salt over the",
                "Add diced raw papaya and sauté for 10 minutes.",
                "Serve hot with roti."
            ]
        })

        recipe = parse_recipe_text(raw_json, fallback_ingredients=["papaya"])
        self.assertIsNotNone(recipe)

        # Confirm headings and incomplete sentences are NOT present in refined instructions
        for step in recipe.instructions:
            self.assertNotIn("For the Papaya Curry", step)
            self.assertNotIn("Prepare the Papaya and Tomato", step)
            self.assertNotIn("Add Spices", step)
            self.assertNotEqual(step.strip(), "Sprinkle salt over the.")
            self.assertTrue(len(step.split()) >= 3, f"Instruction step too short/incomplete: {step}")

    def test_missing_substitutions_diet_safe(self):
        """Scenario 7 & 13: Missing substitutions are generated with culinary logic respecting diet."""
        ingredients = ["200g Paneer cubes", "1 cup Cow's Milk", "2 tbsp Ghee"]
        vegan_subs = generate_culinary_substitutions(ingredients, diet="Vegan")

        # Vegan substitutes must not suggest dairy items!
        for sub in vegan_subs:
            self.assertNotIn("butter", sub.replacement.lower())
            self.assertNotIn("milk", sub.replacement.lower())
            self.assertNotIn("ghee", sub.replacement.lower())
            if "paneer" in sub.ingredient.lower():
                self.assertIn("tofu", sub.replacement.lower())

    def test_missing_shopping_list_derived_from_ingredients(self):
        """Scenario 8: Missing shopping list derived accurately, excluding confirmed pantry."""
        ingredients = ["2 cups Raw papaya, cubed", "1 tsp Fennel seeds", "3 cloves Garlic", "2 tbsp Cooking oil"]
        confirmed_pantry = ["papaya"]  # User already has papaya at home

        shop_list = generate_recipe_shopping_list(ingredients, confirmed_pantry=confirmed_pantry)
        shop_text = " ".join(shop_list).lower()

        # Garlic, fennel seeds, oil should be in shopping list; papaya is confirmed in pantry so excluded
        self.assertTrue("garlic" in shop_text)
        self.assertTrue("fennel" in shop_text)
        self.assertFalse("raw papaya" in shop_text)

    def test_duplicate_ingredients_normalized(self):
        """Scenario 9: Duplicate ingredients are consolidated cleanly."""
        raw_ingredients = [
            "1 tsp Cumin seeds",
            "1/2 tsp Cumin seeds (jeera)",
            "2 medium Tomatoes, pureed",
            "1 chopped Tomato",
        ]
        reconciled, _ = reconcile_ingredients_with_instructions(raw_ingredients, ["Cook everything."])
        # Ensure tomatoes and cumin aren't duplicated into 4 separate entries
        self.assertTrue(len(reconciled) <= 3)

    def test_empty_or_malformed_model_output_activates_fallback(self):
        """Scenario 10 & 11: Empty or malformed model output safely activates database fallback."""
        candidate = {
            "name": "Raw Papaya Sambharo",
            "ingredients_raw": "2 cups Raw papaya grated, 1 tsp Mustard seeds, 1 Green chilli slit, 1/2 tsp Turmeric, 1 tbsp Oil",
            "instructions": "Heat oil in a pan. Add mustard seeds and green chilli. Add grated raw papaya and turmeric. Sauté on medium flame for 3 minutes until crunchy. Serve warm.",
            "cuisine": "Gujarati",
            "diet": "Vegetarian",
        }

        # Empty string
        recipe = parse_recipe_text("", fallback_ingredients=["papaya"], candidate_recipe=candidate)
        self.assertIsNotNone(recipe)
        self.assertEqual(recipe.name, "Raw Papaya Sambharo")
        self.assertTrue(len(recipe.instructions) >= 3)
        self.assertTrue(len(recipe.ingredients) >= 4)

        # Corrupted JSON string
        broken_json = '{"name": "Broken Recipe", "ingredients": ["papaya", '
        recipe_broken = parse_recipe_text(broken_json, fallback_ingredients=["papaya"], candidate_recipe=candidate)
        self.assertIsNotNone(recipe_broken)
        self.assertTrue(len(recipe_broken.instructions) > 0)

    def test_json_bounded_repair(self):
        """Scenario 11: Minor JSON syntax errors (trailing comma, unclosed brackets) are repaired."""
        unclosed = '{"name": "Quick Dal", "description": "Lentils", "ingredients": ["Lentils", "Salt", "Turmeric"], "instructions": ["Boil dal with salt and turmeric."'
        repaired = repair_json_string(unclosed)
        data = json.loads(repaired)
        self.assertEqual(data["name"], "Quick Dal")
        self.assertEqual(len(data["ingredients"]), 3)

    def test_database_fallback_preserves_authentic_data(self):
        """Scenario 12: Database fallback preserves real instructions and ingredients from SQLite candidate."""
        candidate = {
            "name": "Authentic Baingan Bharta",
            "ingredients_raw": "1 large Eggplant roasted and mashed, 1 large Onion chopped, 2 Tomatoes chopped, 4 cloves Garlic minced, 1 tbsp Oil",
            "instructions": "Roast eggplant over open flame until charred. Peel and mash eggplant. Sauté garlic and onions in oil. Add tomatoes and cook down. Mix in mashed eggplant and simmer for 5 minutes.",
            "cuisine": "North Indian",
            "diet": "Vegetarian",
        }

        recipe = create_recipe_from_database_candidate(candidate, confirmed_ingredients=["eggplant"])
        self.assertEqual(recipe.name, "Authentic Baingan Bharta")
        self.assertTrue(any("roasted" in i.lower() or "eggplant" in i.lower() for i in recipe.ingredients))
        self.assertTrue(any("roast" in s.lower() for s in recipe.instructions))
        # Check that substitutions and shopping list are generated
        self.assertTrue(len(recipe.substitutions) > 0)
        self.assertTrue(len(recipe.shopping_list) > 0)

    def test_legitimate_short_instructions_preserved(self):
        """Scenario 14: Legitimate short cooking steps are preserved and not accidentally discarded."""
        step1 = clean_instruction_step("Serve hot.")
        step2 = clean_instruction_step("Serve immediately with warm naan.")
        step3 = clean_instruction_step("Stir well.")
        self.assertIsNotNone(step1)
        self.assertEqual(step1, "Serve hot.")
        self.assertIsNotNone(step2)
        self.assertIsNotNone(step3)

    def test_pydantic_schema_and_response_serialization(self):
        """Scenario 15: Recipe schema handles missing optional fields and serializes safely."""
        minimal_recipe = Recipe(
            name="Simple Khichdi",
            description="Comforting rice and lentil pot.",
            ingredients=["1/2 cup Rice", "1/2 cup Moong Dal", "1/2 tsp Turmeric", "Salt to taste"],
            instructions=["Wash rice and dal.", "Pressure cook with turmeric, salt, and 3 cups water for 3 whistles.", "Serve with ghee."],
            substitutions=[],
            shopping_list=[],
        )
        # Validation pass should auto-populate substitutions and shopping list
        refined, _ = validate_and_refine_recipe(minimal_recipe, confirmed_ingredients=["rice"])
        self.assertTrue(len(refined.shopping_list) > 0)

        response = RecipeResponse(success=True, recipe=refined, raw_text=None)
        json_output = response.model_dump_json()
        self.assertIn("Simple Khichdi", json_output)
        self.assertIn("Moong Dal", json_output)

    def test_recipe_generation_api_route(self):
        """End-to-end integration test of /api/recipe/generate using FastAPI TestClient."""
        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as client:
            payload = {
                "ingredients": ["tomato", "potato"],
                "preferences": {
                    "diet": "Vegetarian",
                    "cuisine": "Indian",
                    "cookingTime": 30,
                    "difficulty": "Easy",
                    "servings": 2,
                    "additionalIngredients": "cumin seeds",
                },
            }
            response = client.post("/api/recipe/generate", json=payload)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["success"])
            self.assertIsNotNone(data["recipe"])
            recipe = data["recipe"]
            self.assertTrue(len(recipe["name"]) > 0)
            self.assertTrue(len(recipe["ingredients"]) > 0)
            self.assertTrue(len(recipe["instructions"]) > 0)
            self.assertTrue(len(recipe["substitutions"]) > 0)
            self.assertTrue(len(recipe["shopping_list"]) > 0)

    def test_clean_fraction_slashes_regex_helper(self):
        """Tests fractional and bare slash normalization for quantities."""
        self.assertEqual(clean_fraction_slashes("/2 cup milk"), "1/2 cup milk")
        self.assertEqual(clean_fraction_slashes("/4 tsp cardamom"), "1/4 tsp cardamom")
        self.assertEqual(clean_fraction_slashes("/2 apple"), "1/2 apple")
        self.assertEqual(clean_fraction_slashes("/ 2 cup milk"), "1/2 cup milk")
        self.assertEqual(clean_fraction_slashes("1 / 2 cup"), "1/2 cup")
        self.assertEqual(clean_fraction_slashes("Apple, /2 chopped"), "Apple, 1/2 chopped")
        # Ensure existing valid fractions are untouched
        self.assertEqual(clean_fraction_slashes("1/2 cup milk"), "1/2 cup milk")
        self.assertEqual(clean_fraction_slashes("3/4 tsp salt"), "3/4 tsp salt")

    def test_recipe_validation_fractional_slashes(self):
        """Tests that validate_and_refine_recipe normalizes bare slash quantities in ingredients and shopping list."""
        test_recipe = Recipe(
            name="Apple Banana Halwa",
            description="Warm fruit halwa prepared on stovetop.",
            ingredients=["/2 cup Milk", "/2 Apple, diced", "- /4 tsp Cardamom powder"],
            instructions=["Heat ghee in a pan.", "Add diced apples and sauté until soft.", "Stir in milk and cardamom powder, simmering until thick."],
            substitutions=[],
            shopping_list=["/2 cup Milk", "/4 tsp Cardamom powder"],
        )
        refined, _ = validate_and_refine_recipe(test_recipe)
        for ing in refined.ingredients:
            self.assertFalse(ing.startswith("/"), f"Ingredient should not start with bare slash: {ing}")
            self.assertFalse(" /" in ing, f"Ingredient should not contain un-prefixed slash: {ing}")
        for item in refined.shopping_list:
            self.assertFalse(item.startswith("/"), f"Shopping item should not start with bare slash: {item}")
        self.assertTrue(any("1/2 cup Milk" in i for i in refined.ingredients))
        self.assertTrue(any("1/2 Apple" in i for i in refined.ingredients))

    def test_recipe_service_stovetop_preference_prompt(self):
        """Tests that RecipeService system prompt enforces standard stovetop preparation over baking."""
        from app.services.recipe_service import RecipeService

        service = RecipeService(use_llm=False)
        req = RecipeRequest(
            ingredients=["apple", "banana", "milk"],
            preferences=RecipePreferences(diet="Vegetarian", cuisine="Indian", cookingTime=20),
        )
        messages = service.build_prompt_and_messages(req.ingredients, req.preferences, candidates=[])
        system_content = messages[0]["content"]

        self.assertIn("STOVETOP PREFERENCE", system_content)
        self.assertIn("kadhai preparation methods", system_content)
        self.assertIn("Do NOT instruct the user to preheat an oven or bake", system_content)

    def test_deduplicate_and_consolidate_semantic_variant_merging(self):
        """Tests that ingredient tokens with variant quantities or prep terms merge into the most descriptive line."""
        # 1. Chillies: "2 Green Chillies" vs "2-3 Green chillies, slit"
        chillies_order1 = ["2 Green Chillies", "2-3 Green chillies, slit"]
        res1 = deduplicate_and_consolidate_ingredients(chillies_order1)
        self.assertEqual(len(res1), 1)
        self.assertEqual(res1[0], "2-3 Green chillies, slit")

        # Reverse order test
        chillies_order2 = ["2-3 Green chillies, slit", "2 Green Chillies"]
        res2 = deduplicate_and_consolidate_ingredients(chillies_order2)
        self.assertEqual(len(res2), 1)
        self.assertEqual(res2[0], "2-3 Green chillies, slit")

        # 2. Onions: "1 medium Onion, finely chopped" vs "2 Onions, sliced"
        onions = ["2 Onions, sliced", "1 medium Onion, finely chopped"]
        res_onions = deduplicate_and_consolidate_ingredients(onions)
        self.assertEqual(len(res_onions), 1)
        self.assertEqual(res_onions[0], "1 medium Onion, finely chopped")

        # 3. Tomatoes: "1 chopped Tomato" vs "2 medium Tomatoes, pureed"
        tomatoes = ["1 chopped Tomato", "2 medium Tomatoes, pureed"]
        res_tomatoes = deduplicate_and_consolidate_ingredients(tomatoes)
        self.assertEqual(len(res_tomatoes), 1)
        self.assertEqual(res_tomatoes[0], "2 medium Tomatoes, pureed")

        # 4. Core extraction helper checks
        self.assertEqual(extract_core_ingredient_key("2 Green Chillies"), "green chilli")
        self.assertEqual(extract_core_ingredient_key("2-3 Green chillies, slit"), "green chilli")
        self.assertEqual(extract_core_ingredient_key("2 Green Chillies – finely chopped"), "green chilli")
        self.assertEqual(extract_core_ingredient_key("2–3 Green chillies, slit or chopped"), "green chilli")
        self.assertEqual(extract_core_ingredient_key("1 chopped Tomato"), "tomato")
        self.assertEqual(extract_core_ingredient_key("2 medium Tomatoes, pureed"), "tomato")

    def test_bulletproof_ingredient_deduplication_dash_variants(self):
        """Tests that en-dashes, em-dashes, and variant phrasing merge into a single clean entry."""
        items = ["2 Green Chillies – finely chopped", "2–3 Green chillies, slit or chopped"]
        res = deduplicate_and_consolidate_ingredients(items)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0], "2-3 Green chillies, slit or chopped")

        # Test shopping list deduplication
        shopping = generate_recipe_shopping_list(
            ingredients=["2 Green Chillies – finely chopped", "2–3 Green chillies, slit or chopped", "Tomatoes, chopped"],
            confirmed_pantry=[],
        )
        self.assertEqual(len([s for s in shopping if "chilli" in s.lower()]), 1)

    def test_culinary_vocabulary_typo_sanitization(self):
        """Tests that small LLM typos like 'sleeve' (strainer) and accidental oven preheating steps are sanitized."""
        sieve_step = clean_instruction_step("Pass the puree through a fine sleeve to discard seeds")
        self.assertEqual(sieve_step, "Pass the puree through a fine sieve to discard seeds.")

        flour_step = clean_instruction_step("Sleeve the flour and spices together into a large bowl")
        self.assertEqual(flour_step, "Sieve the flour and spices together into a large bowl.")

        sleeved_step = clean_instruction_step("Gently fold in the sleeved flour until smooth")
        self.assertEqual(sleeved_step, "Gently fold in the sieved flour until smooth.")

        oven_step = clean_instruction_step("Preheat your oven to 350°F and grease a pan")
        self.assertIn("kadhai", oven_step.lower())
        self.assertNotIn("oven", oven_step.lower())

    def test_exact_match_retrieval_mango(self):
        """Tests that searching for 'mango' returns authentic mango recipes and filters out unrelated produce."""
        from app.services.recipe_retriever import get_recipe_retriever

        retriever = get_recipe_retriever()
        candidates = retriever.retrieve_candidates(["mango"], limit=4)
        self.assertGreaterEqual(len(candidates), 1)

        candidate_names = [c["name"] for c in candidates]
        # Should not return Pineapple Jal Jeera or Besan vegetable (karela)
        self.assertFalse(any("pineapple jal jeera" in name.lower() for name in candidate_names))
        self.assertFalse(any("besan vegetable" in name.lower() for name in candidate_names))

        # Every top returned candidate must feature mango in title or core ingredients
        for c in candidates:
            self.assertTrue(c["has_exact_match"])

    def test_beverage_prevents_inappropriate_protein_injection(self):
        """Tests that beverage recipes strictly prevent solid proteins (paneer, tofu, meat) from being injected."""
        beverage_recipe = Recipe(
            name="Refreshing Pineapple Mint Cooler Drink",
            description="A thirst-quenching chilled summer beverage.",
            ingredients=["2 cups Fresh pineapple chunks", "1/2 cup Chilled water", "200g Paneer cubes", "1 tbsp Honey"],
            instructions=[
                "Chop the fresh pineapple chunks.",
                "Stir in paneer cubes and whole garlic cloves.",
                "Blend until smooth and serve chilled.",
            ],
            substitutions=[],
            shopping_list=[],
        )
        refined, warnings = validate_and_refine_recipe(
            beverage_recipe,
            confirmed_ingredients=["pineapple"],
            diet="Vegetarian",
        )
        # Paneer should be stripped from beverage ingredients
        self.assertFalse(any("paneer" in ing.lower() for ing in refined.ingredients))
        # Garlic should not have been reconciled into beverage
        self.assertFalse(any("garlic" in ing.lower() for ing in refined.ingredients))
        # Substitutions should not recommend tofu for paneer in a drink
        self.assertFalse(any(s.ingredient.lower() == "paneer" for s in refined.substitutions))
        self.assertTrue(any("pineapple" in ing.lower() for ing in refined.ingredients))

    def test_beverage_incorporates_core_ingredients_in_instructions(self):
        """Tests that core ingredients in the title or confirmed pantry (like beetroot and pineapple) are used in steps."""
        beverage_recipe = Recipe(
            name="Beetroot & Pineapple Detox Juice",
            description="Nutrient-packed revitalizing morning beverage.",
            ingredients=["1/2 cup Water", "1 tbsp Honey"],
            instructions=[
                "Wash all produce thoroughly.",
                "Pour into tall glasses and serve chilled.",
            ],
            substitutions=[],
            shopping_list=[],
        )
        refined, _ = validate_and_refine_recipe(
            beverage_recipe,
            confirmed_ingredients=["beetroot", "pineapple"],
            diet="Vegetarian",
        )
        steps_text = " ".join(refined.instructions).lower()
        self.assertIn("beetroot", steps_text)
        self.assertIn("pineapple", steps_text)

        # Both should also be reflected in the ingredients list
        ings_text = " ".join(refined.ingredients).lower()
        self.assertIn("beetroot", ings_text)
        self.assertIn("pineapple", ings_text)

    def test_sanitize_title_and_description_fields(self):
        """Tests that stray JSON fragments, leading colons, and bracket wrappers are stripped from titles/descriptions."""
        # Leading colon with quotes
        self.assertEqual(sanitize_text_field(': "Spiced Beetroot Juice"'), "Spiced Beetroot Juice")
        self.assertEqual(sanitize_text_field(': Spiced Beetroot Juice'), "Spiced Beetroot Juice")
        # Full JSON wrapper
        self.assertEqual(sanitize_text_field('{"name": "Fresh Mango Smoothie"}', field_name="name"), "Fresh Mango Smoothie")
        # Partial JSON fragment
        self.assertEqual(sanitize_text_field('{"name": "Fresh Mango Smoothie"'), "Fresh Mango Smoothie")
        self.assertEqual(sanitize_text_field('name": "Fresh Mango Smoothie"'), "Fresh Mango Smoothie")
        self.assertEqual(sanitize_text_field('"name": "Fresh Mango Smoothie"'), "Fresh Mango Smoothie")
        # Description with stray JSON key
        self.assertEqual(
            sanitize_text_field(': "A refreshing and healthy drink made with seasonal fruits."', field_name="description"),
            "A refreshing and healthy drink made with seasonal fruits.",
        )
        self.assertEqual(
            sanitize_text_field('{"description": "A delicious drink."}', field_name="description"),
            "A delicious drink.",
        )
        self.assertEqual(
            sanitize_text_field('description": "A delicious drink."'),
            "A delicious drink.",
        )
        # Trailing colons and quotes
        self.assertEqual(sanitize_text_field('"Crispy Aloo Methi":'), "Crispy Aloo Methi")
        # Clean title preserved
        self.assertEqual(sanitize_text_field("Tomato & Potato Curry"), "Tomato & Potato Curry")

    def test_handle_raw_json_array_strings_in_ingredients(self):
        """Tests that raw JSON array strings in ingredients or ingredients_raw are parsed and flattened."""
        # Single raw JSON array string
        raw_json_array = '["2 cups chopped beetroot", "1 apple, peeled and cored", "1/2 inch ginger"]'
        flattened = parse_and_flatten_ingredients(raw_json_array)
        self.assertEqual(len(flattened), 3)
        self.assertEqual(flattened[0], "2 cups chopped beetroot")
        self.assertEqual(flattened[1], "1 apple, peeled and cored")
        self.assertEqual(flattened[2], "1/2 inch ginger")

        # List containing an embedded raw JSON array string
        mixed_list = [
            '["1 cup milk", "2 ripe bananas"]',
            "1/2 tsp cardamom powder",
            '["1 tbsp honey"]',
        ]
        flattened_mixed = parse_and_flatten_ingredients(mixed_list)
        self.assertEqual(len(flattened_mixed), 4)
        self.assertEqual(flattened_mixed[0], "1 cup milk")
        self.assertEqual(flattened_mixed[1], "2 ripe bananas")
        self.assertEqual(flattened_mixed[2], "1/2 tsp cardamom powder")
        self.assertEqual(flattened_mixed[3], "1 tbsp honey")

    def test_parse_recipe_text_with_json_syntax_leaks(self):
        """End-to-end test verifying parse_recipe_text cleans raw JSON syntax leaks across all fields."""
        leaky_recipe_output = """
        {
            "name": ": Spiced Beetroot Detox Juice",
            "description": "{\\"description\\": \\"A revitalizing morning juice made with fresh produce.\\"}",
            "ingredients": [
                "[\\"2 medium beetroots, chopped\\", \\"1 large apple, cored\\", \\"1 inch ginger\\"]",
                "1 tbsp lemon juice",
                "Pinch of black salt"
            ],
            "instructions": [
                "Wash and chop all fresh ingredients.",
                "[\\"Place chopped beetroot, apple, and ginger into a blender.\\", \\"Blend until smooth with 1/2 cup chilled water.\\"]",
                "Strain through a fine mesh sieve and stir in lemon juice and black salt before serving."
            ],
            "substitutions": [
                {"ingredient": "\\": Honey\\"", "replacement": "\\": Maple syrup\\""}
            ],
            "shopping_list": [
                "[\\"Beetroots\\", \\"Apples\\"]",
                "Fresh Ginger",
                "Lemon"
            ]
        }
        """
        parsed = parse_recipe_text(
            raw_text=leaky_recipe_output,
            fallback_ingredients=["beetroot", "apple"],
            diet="Vegetarian",
            cuisine="Indian",
        )
        self.assertIsNotNone(parsed)
        # Title must be completely clean without leading colon or quotes
        self.assertEqual(parsed.name, "Spiced Beetroot Detox Juice")
        # Description must be clean without JSON wrappers
        self.assertFalse(parsed.description.startswith("{"))
        self.assertFalse(parsed.description.startswith(":"))
        self.assertIn("revitalizing morning juice", parsed.description)

        # Ingredients must be flattened individual strings, no raw JSON code brackets
        self.assertFalse(any(ing.startswith("[") or ing.endswith("]") for ing in parsed.ingredients))
        self.assertTrue(any("beetroot" in ing.lower() for ing in parsed.ingredients))
        self.assertTrue(any("apple" in ing.lower() for ing in parsed.ingredients))
        self.assertTrue(any("ginger" in ing.lower() for ing in parsed.ingredients))

        # Instructions must be flattened and clean
        self.assertFalse(any(step.startswith("[") or step.endswith("]") for step in parsed.instructions))
        self.assertTrue(any("blender" in step.lower() for step in parsed.instructions))

        # Shopping list must be flattened and clean
        self.assertFalse(any(item.startswith("[") for item in parsed.shopping_list))



if __name__ == "__main__":
    unittest.main()



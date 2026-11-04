"""
Unit and integration tests for DishGenie SQLite recipe database,
retriever, ingredient normalizer, and idempotency.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

# Add backend to path
import sys
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.recipe import RecipePreferences, RecipeRequest, RecipeResponse
from app.services.ingredient_normalizer import (
    classify_recipe_diet,
    extract_ingredient_tokens,
    normalize_cuisine,
    normalize_input_ingredient,
    normalize_token,
)
from app.services.recipe_database import RecipeDatabase
from app.services.recipe_retriever import RecipeRetriever


class TestIngredientNormalizer(unittest.TestCase):
    """Tests for ingredient normalization, synonyms, and diet classification."""

    def test_synonyms_and_botanic_names(self):
        # 247 CNN class botanic name agaricus_bisporus -> mushroom
        self.assertEqual(normalize_input_ingredient("agaricus_bisporus"), "mushroom")
        self.assertEqual(normalize_input_ingredient("agaricus blazei murill"), "mushroom")
        # capsicum / bell pepper
        self.assertEqual(normalize_input_ingredient("bell_pepper"), "capsicum")
        self.assertEqual(normalize_input_ingredient("shimla mirch"), "capsicum")
        # eggplant / brinjal
        self.assertEqual(normalize_input_ingredient("eggplant"), "brinjal")
        self.assertEqual(normalize_input_ingredient("aubergine"), "brinjal")
        # plural stripping
        self.assertEqual(normalize_input_ingredient("tomatoes"), "tomato")
        self.assertEqual(normalize_input_ingredient("potatoes"), "potato")
        self.assertEqual(normalize_input_ingredient("onions"), "onion")

    def test_extract_tokens_preserves_culinary_terms(self):
        cleaned = "tomato,salt,cloves garlic,coriander (dhania) leaves,green chillies"
        tokens = extract_ingredient_tokens(cleaned)
        self.assertIn("tomato", tokens)
        self.assertIn("garlic", tokens)
        self.assertIn("coriander", tokens)
        self.assertIn("green chilli", tokens)

    def test_diet_classification(self):
        # Non-veg
        self.assertEqual(
            classify_recipe_diet("chicken,onion,ginger,garlic", "Butter Chicken"),
            "Non-Vegetarian",
        )
        self.assertEqual(
            classify_recipe_diet("egg,salt,pepper", "Boiled Egg Salad"),
            "Non-Vegetarian",
        )
        self.assertEqual(
            classify_recipe_diet("fish,mustard oil,turmeric", "Bengali Macher Jhol"),
            "Non-Vegetarian",
        )
        # Vegetarian (has dairy)
        self.assertEqual(
            classify_recipe_diet("paneer,tomato,ghee,butter", "Paneer Butter Masala"),
            "Vegetarian",
        )
        self.assertEqual(
            classify_recipe_diet("curd,rice,mustard seeds", "Curd Rice"),
            "Vegetarian",
        )
        # Vegan (pure plant-based, no dairy/eggs/meat)
        self.assertEqual(
            classify_recipe_diet("karela,onion,amchur,oil,salt", "Masala Karela"),
            "Vegan",
        )
        self.assertEqual(
            classify_recipe_diet("tomato,coriander,chickpeas,cumin", "Chole Salad"),
            "Vegan",
        )

    def test_cuisine_normalization(self):
        self.assertEqual(normalize_cuisine("North Indian Recipes"), "Indian")
        self.assertEqual(normalize_cuisine("South Indian Recipes"), "Indian")
        self.assertEqual(normalize_cuisine("Italian Recipes"), "Italian")
        self.assertEqual(normalize_cuisine("Mexican"), "Mexican")
        self.assertEqual(normalize_cuisine("Continental"), "Continental")


class TestRecipeDatabase(unittest.TestCase):
    """Tests for SQLite database operations, schema, and idempotent importing."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_db_path = Path(self.test_dir) / "test_recipes.db"
        self.db = RecipeDatabase(str(self.test_db_path))

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_import_idempotency(self):
        sample_records = [
            {
                "TranslatedRecipeName": "Tomato Rasam Recipe",
                "TranslatedIngredients": "2 Tomatoes, 1 tsp Cumin, 1 tsp Pepper, Salt",
                "Cleaned-Ingredients": "tomato,cumin,pepper,salt",
                "TranslatedInstructions": "Boil tomatoes, add spices, temper with mustard and serve.",
                "Cuisine": "South Indian Recipes",
                "TotalTimeInMins": "20",
                "Ingredient-count": "4",
                "URL": "https://example.com/tomato-rasam-1",
                "image-url": "https://example.com/img1.jpg",
            },
            {
                "TranslatedRecipeName": "Aloo Gobi Dry",
                "TranslatedIngredients": "2 Potatoes, 1 Cauliflower, Turmeric, Salt",
                "Cleaned-Ingredients": "potato,cauliflower,turmeric,salt",
                "TranslatedInstructions": "Chop veggies and saute with spices until tender.",
                "Cuisine": "North Indian Recipes",
                "TotalTimeInMins": "35",
                "Ingredient-count": "4",
                "URL": "https://example.com/aloo-gobi-2",
                "image-url": "https://example.com/img2.jpg",
            },
        ]

        # First run: should insert 2 records
        ins1, skip1 = self.db.insert_recipes_batch(sample_records)
        self.assertEqual(ins1, 2)
        self.assertEqual(skip1, 0)
        self.assertEqual(self.db.count_recipes(), 2)

        # Second run: identical records should be skipped (0 inserted, 2 skipped)
        ins2, skip2 = self.db.insert_recipes_batch(sample_records)
        self.assertEqual(ins2, 0)
        self.assertEqual(skip2, 2)
        self.assertEqual(self.db.count_recipes(), 2)  # Count unchanged

    def test_missing_fields_and_defaults(self):
        # Missing total time and ingredients count
        incomplete_record = {
            "TranslatedRecipeName": "Quick Cucumber Salad",
            "TranslatedIngredients": "1 Cucumber, Lemon juice, Salt",
            "Cleaned-Ingredients": "cucumber,lemon,salt",
            "TranslatedInstructions": "Slice cucumber and toss with lemon juice.",
            "Cuisine": "Indian",
            "TotalTimeInMins": "",  # missing or invalid int
            "URL": "https://example.com/cucumber-salad",
        }
        ins, skip = self.db.insert_recipes_batch([incomplete_record])
        self.assertEqual(ins, 1)

        rec = self.db.get_recipe_by_url("https://example.com/cucumber-salad")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["cooking_time"], 30)  # default applied
        self.assertEqual(rec["name"], "Quick Cucumber Salad")
        self.assertEqual(rec["diet"], "Vegan")

    def test_retrieval_and_dietary_filtering(self):
        records = [
            {
                "TranslatedRecipeName": "Chicken Curry",
                "TranslatedIngredients": "Chicken, Tomato, Onion, Spices",
                "Cleaned-Ingredients": "chicken,tomato,onion",
                "TranslatedInstructions": "Cook chicken in onion-tomato gravy.",
                "Cuisine": "Indian",
                "TotalTimeInMins": "40",
                "URL": "https://example.com/chicken-curry",
            },
            {
                "TranslatedRecipeName": "Paneer Butter Masala",
                "TranslatedIngredients": "Paneer, Tomato, Onion, Butter, Cream",
                "Cleaned-Ingredients": "paneer,tomato,onion,butter,cream",
                "TranslatedInstructions": "Cook paneer in tomato cream sauce.",
                "Cuisine": "Indian",
                "TotalTimeInMins": "30",
                "URL": "https://example.com/paneer-butter",
            },
            {
                "TranslatedRecipeName": "Tomato Onion Salad",
                "TranslatedIngredients": "Tomato, Onion, Lemon, Salt",
                "Cleaned-Ingredients": "tomato,onion,lemon,salt",
                "TranslatedInstructions": "Mix sliced tomato and onion.",
                "Cuisine": "Indian",
                "TotalTimeInMins": "10",
                "URL": "https://example.com/tomato-salad",
            },
        ]
        self.db.insert_recipes_batch(records)
        retriever = RecipeRetriever(self.db)

        # 1. Strict Vegetarian: MUST NOT return Chicken Curry
        veg_prefs = RecipePreferences(diet="Vegetarian", cuisine="Indian", cookingTime=30)
        veg_results = retriever.retrieve_candidates(["tomato", "onion"], veg_prefs)
        veg_names = [r["name"] for r in veg_results]
        self.assertNotIn("Chicken Curry", veg_names)
        self.assertIn("Paneer Butter Masala", veg_names)
        self.assertIn("Tomato Onion Salad", veg_names)

        # 2. Strict Vegan: MUST NOT return Chicken Curry or Paneer Butter Masala (contains dairy)
        vegan_prefs = RecipePreferences(diet="Vegan", cuisine="Indian", cookingTime=30)
        vegan_results = retriever.retrieve_candidates(["tomato", "onion"], vegan_prefs)
        vegan_names = [r["name"] for r in vegan_results]
        self.assertNotIn("Chicken Curry", vegan_names)
        self.assertNotIn("Paneer Butter Masala", vegan_names)
        self.assertIn("Tomato Onion Salad", vegan_names)

        # 3. Non-Vegetarian: Can return all
        non_veg_prefs = RecipePreferences(diet="Non-Vegetarian", cuisine="Indian", cookingTime=45)
        non_veg_results = retriever.retrieve_candidates(["tomato", "onion"], non_veg_prefs)
        non_veg_names = [r["name"] for r in non_veg_results]
        self.assertIn("Chicken Curry", non_veg_names)

    def test_ingredient_overlap_and_ranking(self):
        records = [
            {
                "TranslatedRecipeName": "Triple Match Dish",
                "TranslatedIngredients": "Tomato, Potato, Onion, Spices",
                "Cleaned-Ingredients": "tomato,potato,onion",
                "TranslatedInstructions": "Saute all together.",
                "Cuisine": "Indian",
                "TotalTimeInMins": "30",
                "URL": "https://example.com/triple",
            },
            {
                "TranslatedRecipeName": "Single Match Dish",
                "TranslatedIngredients": "Tomato, Lentils, Salt",
                "Cleaned-Ingredients": "tomato,lentils",
                "TranslatedInstructions": "Boil lentils with tomato.",
                "Cuisine": "Indian",
                "TotalTimeInMins": "30",
                "URL": "https://example.com/single",
            },
        ]
        self.db.insert_recipes_batch(records)
        retriever = RecipeRetriever(self.db)

        prefs = RecipePreferences(diet="Vegetarian", cuisine="Indian", cookingTime=30)
        results = retriever.retrieve_candidates(["tomato", "potato", "onion"], prefs)
        self.assertGreater(len(results), 0)
        # Triple Match should rank higher than Single Match
        self.assertEqual(results[0]["name"], "Triple Match Dish")
        self.assertGreater(results[0]["retrieval_score"], results[1]["retrieval_score"])


class TestRecipeResponseFormatting(unittest.TestCase):
    """Tests for Qwen2.5 output parsing and RecipeResponse contract validation."""

    def test_markdown_and_header_parsing(self):
        from app.services.recipe_parser import parse_recipe_text

        qwen_sample_output = """### RECIPE NAME: Fragrant Spiced Paneer & Capsicum Delight

### DESCRIPTION:
A rich and aromatic North Indian stir-fry dish bursting with roasted spices and tender paneer.

### INGREDIENTS:
- 200g Fresh Paneer cubes
- 1 Large Green Capsicum, diced
- 2 Ripe Red Tomatoes, pureed
- 1 Large Onion, finely chopped
- 1 tsp Cumin seeds
- 1/2 tsp Turmeric powder
- 1 tbsp Cooking oil
- Salt to taste

### INSTRUCTIONS:
1. Heat cooking oil in a heavy-bottomed pan and add cumin seeds until they crackle.
2. Saute finely chopped onions until translucent and golden brown.
3. Add pureed tomatoes, turmeric powder, and salt; simmer for 5 minutes.
4. Toss in diced capsicum and gently fold in the paneer cubes.
5. Cover and cook on low heat for 6-8 minutes until fragrant and serve hot.

### SUBSTITUTIONS:
- Paneer: Firm tofu for a vegan alternative
- Capsicum: Zucchini or sweet bell pepper

### SHOPPING LIST:
- Fresh paneer or firm tofu
- Green bell peppers
- Pureed tomatoes
"""
        recipe = parse_recipe_text(qwen_sample_output, fallback_ingredients=["capsicum", "paneer"])
        self.assertIsNotNone(recipe)
        self.assertEqual(recipe.name, "Fragrant Spiced Paneer & Capsicum Delight")
        self.assertIn("A rich and aromatic", recipe.description)
        self.assertGreaterEqual(len(recipe.ingredients), 5)
        self.assertGreaterEqual(len(recipe.instructions), 5)
        self.assertGreaterEqual(len(recipe.substitutions), 2)
        self.assertGreaterEqual(len(recipe.shopping_list), 3)

    def test_json_output_parsing(self):
        from app.services.recipe_parser import parse_recipe_text

        json_sample = """```json
{
  "name": "Homestyle Aloo Methi",
  "description": "Crispy spiced potatoes with fresh fenugreek greens.",
  "ingredients": ["2 Potatoes diced", "1 cup Fresh Methi leaves", "1 tsp Mustard seeds", "Salt to taste"],
  "instructions": ["Heat oil and splutter mustard seeds.", "Add potatoes and saute until golden.", "Stir in fenugreek leaves and cook until tender."],
  "substitutions": [{"ingredient": "Potatoes", "replacement": "Sweet potatoes"}],
  "shopping_list": ["Fresh methi greens", "Potatoes"]
}
```"""
        recipe = parse_recipe_text(json_sample, fallback_ingredients=["potato"])
        self.assertIsNotNone(recipe)
        self.assertEqual(recipe.name, "Homestyle Aloo Methi")
        self.assertEqual(len(recipe.instructions), 3)
        # Note: Oil mentioned in instruction 1 is reconciled into ingredients (total 5)
        self.assertGreaterEqual(len(recipe.ingredients), 4)
        self.assertTrue(any("oil" in ing.lower() for ing in recipe.ingredients))
        self.assertEqual(len(recipe.substitutions), 1)

    def test_recipe_service_contract_with_database(self):
        from app.services.recipe_service import RecipeService

        service = RecipeService(use_llm=False)
        req = RecipeRequest(
            ingredients=["tomato", "potato", "onion"],
            preferences=RecipePreferences(diet="Vegetarian", cuisine="Indian", cookingTime=30),
        )
        res = service.generate(req)
        self.assertTrue(res.success)
        self.assertIsNotNone(res.recipe)
        self.assertTrue(len(res.recipe.name) > 0)
        self.assertTrue(len(res.recipe.ingredients) > 0)
        self.assertTrue(len(res.recipe.instructions) > 0)
        self.assertTrue(len(res.recipe.shopping_list) > 0)

    def test_recipe_service_candidate_options(self):
        from app.services.recipe_service import RecipeService

        service = RecipeService(use_llm=False)
        req = RecipeRequest(
            ingredients=["karela"],
            preferences=RecipePreferences(diet="Vegetarian", cuisine="Indian"),
        )
        candidates = service.get_candidate_options(req, limit=3)
        self.assertGreaterEqual(len(candidates), 1)
        self.assertLessEqual(len(candidates), 3)
        for opt in candidates:
            self.assertTrue(len(opt["id"]) > 0)
            self.assertTrue(len(opt["name"]) > 0)
            self.assertTrue(len(opt["description"]) > 0)


if __name__ == "__main__":
    unittest.main()


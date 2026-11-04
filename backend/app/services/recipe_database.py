import json
import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

from app.services.ingredient_normalizer import (
    classify_recipe_diet,
    clean_text,
    extract_ingredient_tokens,
    normalize_cuisine,
)

logger = logging.getLogger(__name__)

# Documented default path in backend/data
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "dishgenie_recipes.db"


class RecipeDatabase:
    """
    Local SQLite database layer for DishGenie.
    Provides fast, indexed, and full-text searchable persistent storage for recipes.
    Does NOT load the entire dataset into memory; executes parameterized queries.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else Path(os.getenv("DISHGENIE_DB_PATH", str(DEFAULT_DB_PATH)))
        # Ensure parent data directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager that yields an active SQLite connection with WAL mode
        and Row factory for dictionary-like column access.
        """
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        """
        Initializes the database schema, indexes, FTS5 virtual table, and triggers.
        Safe to call repeatedly (idempotent).
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Main recipes table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recipes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    ingredients_raw TEXT NOT NULL,
                    ingredients_cleaned TEXT NOT NULL,
                    ingredients_tokens TEXT NOT NULL,
                    instructions TEXT NOT NULL,
                    cuisine TEXT NOT NULL,
                    cuisine_category TEXT NOT NULL,
                    diet TEXT NOT NULL,
                    cooking_time INTEGER NOT NULL DEFAULT 30,
                    ingredient_count INTEGER NOT NULL DEFAULT 0,
                    url TEXT UNIQUE NOT NULL,
                    image_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 2. Indexes for fast filtered queries
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_recipes_url ON recipes(url);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipes_diet ON recipes(diet);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipes_cuisine_cat ON recipes(cuisine_category);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipes_time ON recipes(cooking_time);")

            # 3. Normalized relational ingredient tokens mapping table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recipe_ingredients (
                    recipe_id INTEGER NOT NULL,
                    token TEXT NOT NULL,
                    PRIMARY KEY (recipe_id, token),
                    FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipe_ing_token ON recipe_ingredients(token);")

            # 4. FTS5 Virtual Table for full-text queries
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS recipes_fts USING fts5(
                    name,
                    ingredients_cleaned,
                    cuisine,
                    content='recipes',
                    content_rowid='id'
                );
            """)

            # 5. FTS5 Sync Triggers
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS recipes_ai AFTER INSERT ON recipes BEGIN
                    INSERT INTO recipes_fts(rowid, name, ingredients_cleaned, cuisine)
                    VALUES (new.id, new.name, new.ingredients_cleaned, new.cuisine);
                END;
            """)
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS recipes_ad AFTER DELETE ON recipes BEGIN
                    INSERT INTO recipes_fts(recipes_fts, rowid, name, ingredients_cleaned, cuisine)
                    VALUES ('delete', old.id, old.name, old.ingredients_cleaned, old.cuisine);
                END;
            """)
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS recipes_au AFTER UPDATE ON recipes BEGIN
                    INSERT INTO recipes_fts(recipes_fts, rowid, name, ingredients_cleaned, cuisine)
                    VALUES ('delete', old.id, old.name, old.ingredients_cleaned, old.cuisine);
                    INSERT INTO recipes_fts(rowid, name, ingredients_cleaned, cuisine)
                    VALUES (new.id, new.name, new.ingredients_cleaned, new.cuisine);
                END;
            """)

            logger.info(f"[RecipeDatabase] Database initialized at: {self.db_path.resolve()}")

    def count_recipes(self) -> int:
        """Returns total number of recipes currently in the database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM recipes;")
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def get_recipe_by_id(self, recipe_id: int) -> Optional[Dict[str, Any]]:
        """Fetches a single recipe by its primary key."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM recipes WHERE id = ?;", (recipe_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_recipe_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetches a single recipe by its unique URL."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM recipes WHERE url = ?;", (url,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def insert_recipe(self, data: Dict[str, Any]) -> bool:
        """
        Inserts a single recipe idempotently. Returns True if inserted, False if duplicate.
        """
        inserted, _ = self.insert_recipes_batch([data])
        return inserted > 0

    def insert_recipes_batch(self, records: List[Dict[str, Any]]) -> Tuple[int, int]:
        """
        Inserts a batch of recipes into SQLite within a single transaction.
        Uses INSERT OR IGNORE on the unique `url` constraint to prevent duplicates.
        Populates both `recipes` and `recipe_ingredients`.
        Returns:
            Tuple[int, int]: (inserted_count, skipped_count)
        """
        if not records:
            return 0, 0

        inserted_count = 0
        skipped_count = 0

        with self.get_connection() as conn:
            cursor = conn.cursor()

            for rec in records:
                url = clean_text(str(rec.get("URL", rec.get("url", ""))))
                if not url:
                    skipped_count += 1
                    continue

                name = clean_text(str(rec.get("TranslatedRecipeName", rec.get("name", "Untitled Recipe"))))
                ing_raw = clean_text(str(rec.get("TranslatedIngredients", rec.get("ingredients_raw", ""))))
                ing_clean = clean_text(str(rec.get("Cleaned-Ingredients", rec.get("ingredients_cleaned", "")))) or ing_raw
                instructions = clean_text(str(rec.get("TranslatedInstructions", rec.get("instructions", ""))))
                # some rows ship untranslated Hindi instructions: unusable for English recipes
                if len(re.findall(r"[ऀ-ॿ]", instructions)) > len(instructions) * 0.1:
                    skipped_count += 1
                    continue
                cuisine = clean_text(str(rec.get("Cuisine", rec.get("cuisine", "Indian"))))
                image_url = clean_text(str(rec.get("image-url", rec.get("image_url", ""))))

                try:
                    cooking_time = int(rec.get("TotalTimeInMins", rec.get("cooking_time", 30)))
                    if cooking_time <= 0:
                        cooking_time = 30
                except (ValueError, TypeError):
                    cooking_time = 30

                try:
                    ing_count = int(rec.get("Ingredient-count", rec.get("ingredient_count", 0)))
                except (ValueError, TypeError):
                    ing_count = len(ing_clean.split(",")) if ing_clean else 0

                # Derive normalization
                tokens = extract_ingredient_tokens(ing_clean)
                tokens_json = json.dumps(tokens)
                diet = classify_recipe_diet(ing_clean, name)
                if re.search(r"non[\s-]*veg", str(rec.get("Diet", "")), re.I):
                    diet = "Non-Vegetarian"
                cuisine_category = normalize_cuisine(cuisine)

                # Parameterized idempotent insert
                cursor.execute("""
                    INSERT OR IGNORE INTO recipes (
                        name, ingredients_raw, ingredients_cleaned, ingredients_tokens,
                        instructions, cuisine, cuisine_category, diet, cooking_time,
                        ingredient_count, url, image_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    name, ing_raw, ing_clean, tokens_json, instructions, cuisine,
                    cuisine_category, diet, cooking_time, ing_count, url, image_url
                ))

                if cursor.rowcount > 0:
                    recipe_id = cursor.lastrowid
                    inserted_count += 1

                    # Insert relational tokens
                    for tok in tokens:
                        cursor.execute("""
                            INSERT OR IGNORE INTO recipe_ingredients (recipe_id, token)
                            VALUES (?, ?);
                        """, (recipe_id, tok))
                else:
                    skipped_count += 1

        return inserted_count, skipped_count


# Singleton global instance
_recipe_db_instance: Optional[RecipeDatabase] = None


def get_recipe_database() -> RecipeDatabase:
    """Returns the shared RecipeDatabase instance."""
    global _recipe_db_instance
    if _recipe_db_instance is None:
        _recipe_db_instance = RecipeDatabase()
    return _recipe_db_instance

# DishGenie

Photo of ingredients -> confirmed ingredient list -> dish options -> step-by-step recipe. Fully local (no cloud APIs).

## How it works
1. **Detect** (`/api/vision/predict`): a local vision LLM (Ollama `gemma3:4b`) decides which ingredients are in the photo.
   The bundled 247-class Keras CNN + YOLO-World region proposer add boxes, counts and freshness/expiry estimates.
   If Ollama is down, the CNN pipeline alone is used.
2. **Dish options** (`/api/recipe/candidates`): top 3 matching recipes from a SQLite/FTS5 database of ~6,300 Indian recipes.
3. **Generate** (`/api/recipe/generate`): Ollama `llama3.2` writes the recipe as JSON. The service checks every confirmed
   ingredient is used (one retry), then validates diet/ingredients/shopping list. Falls back to the database recipe if the LLM fails.

## Setup (Windows)
Prerequisites: Python 3.12, Node 20+, [Ollama](https://ollama.com).
```powershell
ollama pull llama3.2
ollama pull gemma3:4b

cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# recipe data: put Cleaned_Indian_Food_Dataset.csv (or the public IndianFoodDatasetCSV.csv, same columns) in backend/data/
.\.venv\Scripts\python.exe scripts\import_recipes.py

cd ..\frontend
npm install
cd ..
.\start.ps1
```
Open http://localhost:5173.

## Config (env vars, backend)
`GENAI_MODEL` (default `llama3.2`), `VISION_LLM_MODEL` (default `gemma3:4b`), `VISION_LLM_ENABLED`, `OLLAMA_URL`,
`GENAI_TIMEOUT`, `DISHGENIE_DB_PATH`. Frontend: `VITE_API_URL` (default `http://localhost:8000`).

## Tests
From the repo root: `set PYTHONPATH=.` then `backend\.venv\Scripts\python.exe -m pytest backend\tests`.

## Known limits
- Vision LLM counts are rough (the inventory table lets you edit them); it can occasionally add a look-alike item,
  which is why the UI asks you to confirm ingredients.
- 6 GB GPUs hold both Ollama models, but the first request after idle reloads them (~10-20 s).
- TensorFlow runs on CPU on native Windows.

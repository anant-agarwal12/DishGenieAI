import os

# CNN-pipeline tests use synthetic images; keep the live vision LLM out of them
os.environ["VISION_LLM_ENABLED"] = "false"

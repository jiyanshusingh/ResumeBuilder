import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", BASE_DIR / "output"))
TEMPLATE_DIR = BASE_DIR / "templates"
TEMPLATE_PATH = TEMPLATE_DIR / "resume_template.tex.j2"

PORT = int(os.environ.get("PORT", 7860))
HOST = os.environ.get("HOST", "0.0.0.0")
SHARE = os.environ.get("SHARE", "false").lower() == "true"

DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

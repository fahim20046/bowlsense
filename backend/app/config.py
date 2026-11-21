"""App configuration (env-overridable)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
STORAGE_DIR = Path(os.getenv("BOWLSENSE_STORAGE", BASE_DIR.parent / "storage"))
MODEL_DIR = BASE_DIR / "models"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(STORAGE_DIR / 'bowlsense.db').as_posix()}")

POSE_MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
                  "pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task")  # heavy == model_complexity=2
POSE_MODEL_PATH = MODEL_DIR / "pose_landmarker_heavy.task"

ALLOWED_EXT = {".mp4", ".mov", ".avi"}
MAX_UPLOAD_MB = 500
VIS_THRESHOLD = 0.5
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)

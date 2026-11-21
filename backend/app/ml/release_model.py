"""Trained release-frame detector (gradient-boosted trees on pose features). Optional: if the model file is
missing the app falls back to the rule-based detector."""
from functools import lru_cache
from typing import Optional

import numpy as np

from ..config import MODEL_DIR
from ..modules.kinematics import Kin
from .features import frame_features

MODEL_PATH = MODEL_DIR / "release_model.joblib"
MIN_PROB = 0.15          # below this peak probability the model is unsure -> fall back to the rule


@lru_cache(maxsize=1)
def _load():
    if not MODEL_PATH.exists():
        return None
    import joblib
    return joblib.load(MODEL_PATH)


def available() -> bool:
    return _load() is not None


def release_probabilities(k: Kin) -> Optional[np.ndarray]:
    m = _load()
    if m is None:
        return None
    X, _ = frame_features(k)
    p = m.predict_proba(X)[:, 1]
    p[~np.isfinite(k.P[:, 23, 0])] = 0.0                     # only frames where the bowler is tracked
    return np.convolve(p, np.ones(3) / 3, mode="same")       # light temporal smoothing


def predict_release(k: Kin, start: int = 0) -> tuple[Optional[int], float]:
    """(frame, peak probability) or (None, 0) if no model / not confident."""
    p = release_probabilities(k)
    if p is None or start >= len(p):
        return None, 0.0
    p = p.copy()
    p[:start] = 0
    f = int(np.argmax(p))
    return (f, float(p[f])) if p[f] >= MIN_PROB else (None, float(p[f]))

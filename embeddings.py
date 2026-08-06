"""Lightweight embedding utilities using sentence-transformers.

The model is loaded lazily and cached. If torch/sentence-transformers or the
model file is unavailable, `available()` returns False and callers can fall
back to their rule-based implementations (matching the app's existing
degrade-gracefully pattern).
"""

from __future__ import annotations

import json
import os
import threading
from typing import List, Optional

try:  # data dir for the persistent disk cache
    from config import DATA_DIR

    _CACHE_FILE = DATA_DIR / "cache" / "embeddings.json"
except Exception:  # pragma: no cover
    _CACHE_FILE = None


DEFAULT_MODEL = "all-MiniLM-L6-v2"

_model = None
_model_lock = threading.Lock()
_cache_lock = threading.Lock()
_cache: dict = {}

_disable_reason: Optional[str] = None


def _load_disk_cache():
    if _CACHE_FILE is None or not _CACHE_FILE.exists():
        return {}
    try:
        with open(_CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


_cache.update(_load_disk_cache())


def _flush_disk_cache():
    if _CACHE_FILE is None:
        return
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_FILE, "w") as f:
            json.dump(_cache, f)
    except Exception:
        pass


def _enabled() -> bool:
    return os.environ.get("RESUME_EMBEDDINGS", "1") != "0"


def available() -> bool:
    """Return True if the embedding model can be loaded.

    Honors RESUME_EMBEDDINGS=0 to disable all model use (e.g. hermetic CI).
    """
    if not _enabled():
        return False
    _get_model()
    return _model is not None


def _get_model():
    global _model, _disable_reason
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(DEFAULT_MODEL)
        except Exception as exc:  # pragma: no cover - depends on env
            _disable_reason = f"{type(exc).__name__}: {exc}"
            _model = None
    return _model


def embed(text: str) -> Optional[List[float]]:
    """Embed a single text. Returns None when unavailable.

    Vectors are cached in memory and persisted to a JSON file on disk so
    re-embeds are instant across process restarts (offline).
    """
    if not text or not str(text).strip():
        return None
    key = str(text).strip()
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None:
            return cached
    model = _get_model()
    if model is None:
        return None
    try:
        vector = model.encode([key], normalize_embeddings=True)[0]
    except Exception:  # pragma: no cover - depends on env
        return None
    with _cache_lock:
        _cache[key] = vector
    _flush_disk_cache()
    return vector


def similarity(text_a: str, text_b: str) -> Optional[float]:
    """Cosine similarity between two texts. None when unavailable."""
    va = embed(text_a)
    vb = embed(text_b)
    if va is None or vb is None:
        return None
    return float(sum(x * y for x, y in zip(va, vb)))


def status() -> str:
    """Human-readable status for the UI."""
    _get_model()
    if _model is not None:
        return f"active ({DEFAULT_MODEL})"
    if _disable_reason:
        return f"unavailable ({_disable_reason})"
    return "unavailable"

"""
model_runtime/providers/cross_encoder_provider.py
Cross-encoder reranker provider (Rule 5).

B1 fix: the CrossEncoder is loaded lazily via a singleton instead of at import.
memory.py previously loaded it at module import time.
"""

from __future__ import annotations

from threading import Lock
from typing import Any

from config.memory_settings import RERANKER_MODEL

_reranker: Any | None = None
_lock = Lock()


def get_reranker() -> Any:
    """Return the loaded CrossEncoder reranker, loading it once on first call."""
    global _reranker
    if _reranker is None:
        with _lock:
            if _reranker is None:
                from sentence_transformers import CrossEncoder

                _reranker = CrossEncoder(RERANKER_MODEL)
    return _reranker


def rerank_scores(pairs: list[tuple[str, str]]) -> list[float]:
    """Predict relevance scores for (query, document) pairs."""
    return [float(s) for s in get_reranker().predict(pairs)]

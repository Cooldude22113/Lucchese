"""
model_runtime/providers/sentence_transformer_provider.py
Embedding-function provider for ChromaDB (Rule 5).

B1 fix: the SentenceTransformer embedding function is built lazily via a singleton
rather than at module import. memory.py previously instantiated it at import time.
"""

from __future__ import annotations

from threading import Lock
from typing import Any

from config.memory_settings import EMBED_MODEL

_embedding_fn: Any | None = None
_lock = Lock()


def get_embedding_function() -> Any:
    """
    Return the Chroma-compatible SentenceTransformer embedding function, built once
    on first call. Passed to chroma get_or_create_collection(embedding_function=...).
    """
    global _embedding_fn
    if _embedding_fn is None:
        with _lock:
            if _embedding_fn is None:
                from chromadb.utils import embedding_functions

                _embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name=EMBED_MODEL,
                    trust_remote_code=True,
                )
    return _embedding_fn

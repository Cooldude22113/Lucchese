"""
memory/collections/chroma_client.py
The shared ChromaDB PersistentClient (Rule 6/7, Rule 9 mechanics).

Lazy singleton so importing this module never opens the store. The path comes from
config/paths.py (Rule 1).
"""

from __future__ import annotations

from threading import Lock
from typing import Any

from config.paths import CHROMA_PATH

_client: Any | None = None
_lock = Lock()


def get_client() -> Any:
    """Return the cached PersistentClient, creating it once on first call."""
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                import chromadb

                _client = chromadb.PersistentClient(path=CHROMA_PATH)
    return _client

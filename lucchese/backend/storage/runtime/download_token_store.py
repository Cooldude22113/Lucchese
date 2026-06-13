"""
storage/runtime/download_token_store.py
In-memory token -> filepath store for generated-document downloads (Rule 9).

Runtime state, not persisted. The document lifecycle (cleanup) lives in
documents/lifecycle/; this module only owns the mapping.
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

_doc_store: dict[str, str] = {}
_doc_lock = threading.Lock()


def store_doc_token(filepath: str) -> tuple[str, str]:
    """Store a filepath under a fresh token. Returns (token, filename)."""
    token = uuid.uuid4().hex
    filename = Path(filepath).name
    with _doc_lock:
        _doc_store[token] = filepath
    return token, filename


def get_doc_path(token: str) -> str | None:
    """Return the filepath for a token, or None if unknown/expired."""
    with _doc_lock:
        return _doc_store.get(token)


def pop_doc_path(token: str) -> str | None:
    """Remove and return the filepath for a token (used by cleanup)."""
    with _doc_lock:
        return _doc_store.pop(token, None)

"""
memory/collections/collection_registry.py
Named access to the five ChromaDB collections (Rule 7: split memory by stage).

Collections are created on first access via get_or_create_collection with the shared
embedding function, then cached. Callers use the named getters instead of holding
module-level collection objects, so nothing is created at import time (B1).
"""

from __future__ import annotations

from typing import Any

from memory.collections.chroma_client import get_client
from model_runtime.providers.sentence_transformer_provider import get_embedding_function

COLLECTION_NAMES = ("knowledge", "facts", "style", "documents", "summaries")

_collections: dict[str, Any] = {}


def get_collection(name: str) -> Any:
    """Return (creating + caching on first use) the named collection."""
    if name not in _collections:
        _collections[name] = get_client().get_or_create_collection(
            name, embedding_function=get_embedding_function()
        )
    return _collections[name]


def get_knowledge() -> Any:
    return get_collection("knowledge")


def get_facts() -> Any:
    return get_collection("facts")


def get_style() -> Any:
    return get_collection("style")


def get_documents() -> Any:
    return get_collection("documents")


def get_summaries() -> Any:
    return get_collection("summaries")

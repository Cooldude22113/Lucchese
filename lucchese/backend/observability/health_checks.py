"""
observability/health_checks.py
Public health snapshot — ChromaDB collection counts (Rule 15).
"""

from __future__ import annotations

from memory.collections.collection_registry import (
    get_documents,
    get_facts,
    get_knowledge,
    get_style,
)


def health_snapshot() -> dict:
    """Collection counts for the public /health endpoint."""
    return {
        "status": "ok",
        "knowledge": get_knowledge().count(),
        "facts": get_facts().count(),
        "style": get_style().count(),
        "documents": get_documents().count(),
    }

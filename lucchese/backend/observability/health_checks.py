"""
observability/health_checks.py
Public health snapshot — ChromaDB collection counts + Ollama reachability (Rule 15).
"""

from __future__ import annotations

from config.model_settings import CHAT_PROVIDER
from memory.collections.collection_registry import (
    get_documents,
    get_facts,
    get_knowledge,
    get_style,
)
from model_runtime.providers.ollama_provider import check_availability


def health_snapshot() -> dict:
    """Collection counts plus an Ollama reachability block for the public /health endpoint."""
    return {
        "status": "ok",
        "knowledge": get_knowledge().count(),
        "facts": get_facts().count(),
        "style": get_style().count(),
        "documents": get_documents().count(),
        "ollama": _ollama_health(),
    }


def _ollama_health() -> dict:
    """Best-effort Ollama probe; never raises so /health always returns 200."""
    try:
        reachable, models, detail = check_availability(timeout=3.0)
        return {
            "provider": CHAT_PROVIDER,
            "reachable": reachable,
            "models": len(models),
            "detail": detail,
        }
    except Exception as exc:  # defensive — check_availability already swallows errors
        return {"provider": CHAT_PROVIDER, "reachable": False, "models": 0, "detail": str(exc)}

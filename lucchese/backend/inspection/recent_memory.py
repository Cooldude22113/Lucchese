"""
inspection/recent_memory.py
Most recently ingested facts (Rule 17, read-only).
"""

from __future__ import annotations

from memory.collections.collection_registry import get_facts


def recent_facts(limit: int = 20) -> list[dict]:
    """Return the most recent facts, newest first, truncated for display."""
    results = get_facts().get(include=["documents", "metadatas"], limit=500)
    items = [
        {
            "text":       doc[:120],
            "source":     meta.get("source", "unknown"),
            "category":   meta.get("category", "general"),
            "created_at": meta.get("created_at", ""),
            "conv_id":    meta.get("conv_id", ""),
        }
        for doc, meta in zip(results["documents"], results["metadatas"])
    ]
    items.sort(key=lambda x: x["created_at"] or "", reverse=True)
    return items[:limit]

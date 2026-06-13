"""
inspection/raw_debug_dump.py
Raw dump of the knowledge collection for dev inspection (Rule 17).
"""

from __future__ import annotations

from memory.collections.collection_registry import get_knowledge


def dump_knowledge() -> list[dict]:
    """First 100 chars of each knowledge entry, newest first."""
    results = get_knowledge().get(include=["documents", "metadatas"])
    items = [
        {
            "text":       doc[:100],
            "created_at": meta.get("created_at"),
            "source":     meta.get("source"),
            "type":       meta.get("type"),
        }
        for doc, meta in zip(results["documents"], results["metadatas"])
    ]
    items.sort(key=lambda x: x["created_at"] or "", reverse=True)
    return items

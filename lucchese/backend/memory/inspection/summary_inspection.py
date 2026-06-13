"""
memory/inspection/summary_inspection.py
Read-only listing of generated summaries (Rule 17).
"""

from __future__ import annotations

from memory.collections.collection_registry import get_summaries


def list_summaries() -> list[dict] | dict:
    """All summaries, sorted by entry count descending. Returns {'error': ...} on failure."""
    try:
        results = get_summaries().get(include=["documents", "metadatas"])
        items = [
            {
                "category":     meta.get("category"),
                "entry_count":  meta.get("entry_count"),
                "last_updated": meta.get("last_updated"),
                "summary":      doc,
            }
            for doc, meta in zip(results["documents"], results["metadatas"])
        ]
        items.sort(key=lambda x: int(x["entry_count"] or 0), reverse=True)
        return items
    except Exception as e:
        return {"error": str(e)}

"""
memory/ingestion/summary_ingestor.py
Write per-category summaries into the summaries collection (Rule 8).
"""

from __future__ import annotations

from memory.collections.collection_registry import get_summaries


def upsert_summary(category: str, summary_text: str, entry_count: int, now: str) -> None:
    """Upsert a single per-category summary (one entry per category)."""
    get_summaries().upsert(
        ids=[f"summary_{category}"],
        documents=[summary_text],
        metadatas=[{
            "category":     category,
            "entry_count":  str(entry_count),
            "last_updated": now,
            "type":         "summary",
        }],
    )

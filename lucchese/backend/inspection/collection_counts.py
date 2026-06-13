"""
inspection/collection_counts.py
Read-only counting of a ChromaDB collection by source and category (Rule 17).
"""

from __future__ import annotations


def count_by_source_and_category(collection, batch: int = 500) -> dict:
    """
    Page through a collection's metadatas and tally source/category counts.
    Returns {"total", "by_source", "by_category"}.
    """
    source_counts: dict = {}
    category_counts: dict = {}
    offset = 0

    while True:
        results = collection.get(include=["metadatas"], limit=batch, offset=offset)
        metas = results["metadatas"]
        if not metas:
            break
        for m in metas:
            src = m.get("source", "unknown")
            cat = m.get("category", "general")
            source_counts[src] = source_counts.get(src, 0) + 1
            category_counts[cat] = category_counts.get(cat, 0) + 1
        offset += batch

    return {
        "total": collection.count(),
        "by_source": source_counts,
        "by_category": category_counts,
    }

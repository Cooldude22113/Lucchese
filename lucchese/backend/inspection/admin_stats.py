"""
inspection/admin_stats.py
Memory collection statistics for the admin panel (Rule 17, read-only).
"""

from __future__ import annotations

from inspection.collection_counts import count_by_source_and_category
from memory.collections.collection_registry import get_facts, get_knowledge, get_style


def admin_stats() -> dict:
    """Per-collection totals and source/category breakdowns for knowledge/facts/style."""
    stats: dict = {}
    for col, name in [
        (get_knowledge(), "knowledge"),
        (get_facts(), "facts"),
        (get_style(), "style"),
    ]:
        stats[name] = count_by_source_and_category(col)
    return stats

"""
inspection/semantic_search.py
Semantic search across the facts collection for the admin panel (Rule 17).
"""

from __future__ import annotations

from memory.collections.collection_registry import get_facts


def search_facts(query: str, n: int = 10) -> list[dict]:
    """Return up to n facts matching the query, with a relevance score."""
    results = get_facts().query(
        query_texts=[query],
        n_results=n,
        include=["documents", "metadatas", "distances"],
    )
    return [
        {
            "text":       doc[:200],
            "source":     meta.get("source", "unknown"),
            "category":   meta.get("category", "general"),
            "created_at": meta.get("created_at", ""),
            "relevance":  round(1 / (1 + dist), 3),
        }
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ]

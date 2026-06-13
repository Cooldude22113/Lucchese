"""
memory/processing/deduplication.py
Near-duplicate detection before writing memory (Rule 7).
"""

from __future__ import annotations

import logging

from config.memory_settings import SIMILARITY_THRESHOLD

logger = logging.getLogger(__name__)


def is_duplicate_memory(text: str, collection, n: int = 1) -> bool:
    """
    True if a chunk within SIMILARITY_THRESHOLD (L2 distance) already exists in the
    collection. On query failure, returns False (allow the write) and logs.
    """
    try:
        results = collection.query(query_texts=[text], n_results=n, include=["distances"])
        if results["distances"] and results["distances"][0]:
            closest_distance = results["distances"][0][0]
            return closest_distance < SIMILARITY_THRESHOLD
    except Exception as e:
        logger.warning("is_duplicate_memory check failed: %s — allowing write", e)
    return False

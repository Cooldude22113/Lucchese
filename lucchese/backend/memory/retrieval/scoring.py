"""
memory/retrieval/scoring.py
Recency and final-score math for retrieval ranking (Rule 7).
"""

from __future__ import annotations

import math
from datetime import datetime

from config.memory_settings import RECENCY_WEIGHT


def recency_factor(created_at_iso: str, now_ts: float) -> float:
    """
    Exponential recency decay (half-life ~1 year). Defaults to 0.5 if the
    timestamp is missing or unparseable.
    """
    try:
        created_ts = datetime.fromisoformat(created_at_iso).timestamp()
        age_days = (now_ts - created_ts) / 86400
        return math.exp(-age_days / 365)
    except Exception:
        return 0.5


def final_score(reranker_score: float, recency: float, is_fact: bool) -> float:
    """Combine cross-encoder score with recency and a small fact bonus."""
    recency_bonus = recency * RECENCY_WEIGHT
    fact_bonus = 0.05 if is_fact else 0.0
    return float(reranker_score) + recency_bonus + fact_bonus

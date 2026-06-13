"""
memory/retrieval/reranking.py
Cross-encoder reranking of retrieval candidates (Rule 7).

Takes the raw pulled chunks and returns scored (score, label, doc) tuples. On
reranker failure, degrades to recency-only scoring so retrieval still returns
something.
"""

from __future__ import annotations

from memory.retrieval.scoring import final_score
from model_runtime.providers.cross_encoder_provider import rerank_scores


def rerank(query: str, raw_chunks: list[dict]) -> list[tuple[float, str, str]]:
    """
    raw_chunks items: {"label", "doc", "recency", "is_fact"}.
    Returns a list of (score, label, doc) candidates (unsorted).
    """
    if not raw_chunks:
        return []

    candidates: list[tuple[float, str, str]] = []
    try:
        pairs = [(query, c["doc"]) for c in raw_chunks]
        scores = rerank_scores(pairs)
        for chunk, score in zip(raw_chunks, scores):
            candidates.append((
                final_score(score, chunk["recency"], chunk["is_fact"]),
                chunk["label"],
                chunk["doc"],
            ))
    except Exception as e:
        print(f"Reranker error: {e}")
        for chunk in raw_chunks:
            candidates.append((chunk["recency"], chunk["label"], chunk["doc"]))

    return candidates

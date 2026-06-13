"""
memory/retrieval/semantic_search.py
The RAG retrieval pipeline (Rule 6/7).

  1. Pull relevant category summaries (weighted up).
  2. Expand the query into multiple phrasings.
  3. Pull candidate chunks from knowledge/facts/style/documents.
  4. Rerank with the cross-encoder (+ recency / fact bonuses).
  5. Sort, deduplicate, and return the top results as a formatted string.

Returns a pre-formatted string (not a list) — consumers inject it into the prompt.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from memory.collections.collection_registry import (
    get_documents,
    get_facts,
    get_knowledge,
    get_style,
    get_summaries,
)
from memory.retrieval.query_expansion import expand_query
from memory.retrieval.reranking import rerank
from memory.retrieval.scoring import recency_factor

logger = logging.getLogger(__name__)


async def search_memory(query: str, n: int = 5) -> str:
    candidates: list[tuple[float, str, str]] = []
    now_ts = datetime.now(timezone.utc).timestamp()

    # ── Step 1: relevant summaries ────────────────────────────────────────────
    try:
        summary_hits = get_summaries().query(
            query_texts=[query],
            n_results=3,
            include=["documents", "distances", "metadatas"],
        )
        for doc, dist, meta in zip(
            summary_hits["documents"][0],
            summary_hits["distances"][0],
            summary_hits["metadatas"][0],
        ):
            if not doc.strip():
                continue
            relevance = 1 / (1 + dist)
            if relevance > 0.3:
                candidates.append((
                    relevance * 1.4,
                    f"Summary ({meta.get('category', 'general')})",
                    doc.strip(),
                ))
    except Exception as e:
        logger.error("Summary search error: %s", e)

    # ── Step 2: expand query and pull chunks ──────────────────────────────────
    queries = await expand_query(query)
    raw_chunks: list[dict] = []
    seen_docs: set[str] = set()

    for col, label in [
        (get_knowledge(), "Past conversation"),
        (get_facts(),     "Things you've said"),
        (get_style(),     "Your writing style"),
        (get_documents(), "Your documents"),
    ]:
        try:
            for q in queries:
                hits = col.query(
                    query_texts=[q],
                    n_results=n * 2,
                    include=["documents", "distances", "metadatas"],
                )
                for doc, dist, meta in zip(
                    hits["documents"][0],
                    hits["distances"][0],
                    hits["metadatas"][0],
                ):
                    if not doc.strip():
                        continue
                    doc_key = doc[:100]
                    if doc_key in seen_docs:
                        continue
                    seen_docs.add(doc_key)

                    recency = recency_factor(meta.get("created_at", ""), now_ts)

                    display_text = doc.strip()
                    if label == "Past conversation" and meta.get("user_text_raw"):
                        assistant_exc = meta.get("assistant_excerpt", "")
                        display_text = meta["user_text_raw"].strip()
                        if assistant_exc:
                            display_text += f"\n→ {assistant_exc[:200]}"

                    raw_chunks.append({
                        "label":   label,
                        "doc":     display_text,
                        "recency": recency,
                        "is_fact": label == "Things you've said",
                    })
        except Exception as e:
            print(f"search_memory error ({label}): {e}")

    # ── Step 3: rerank ────────────────────────────────────────────────────────
    candidates.extend(rerank(query, raw_chunks))

    # ── Step 4: sort, deduplicate, return ─────────────────────────────────────
    candidates.sort(key=lambda x: x[0], reverse=True)

    seen: set[str] = set()
    top: list[tuple[str, str]] = []
    for _score, label, doc in candidates:
        key = doc[:100]
        if key in seen:
            continue
        seen.add(key)
        top.append((label, doc))
        if len(top) >= 10:
            break

    if not top:
        return ""

    return "\n\n".join(f"[{label}]: {doc}" for label, doc in top)

"""
memory/retrieval/query_expansion.py
Generate alternative phrasings of a query to widen retrieval (Rule 7).

Uses the local Ollama model. Returns the original query plus up to 2 expansions;
falls back to just the original on any failure.
"""

from __future__ import annotations

import logging

from config.model_settings import MODEL_FAST, QUERY_EXPANSION_TIMEOUT
from model_runtime.providers import ollama_provider

logger = logging.getLogger(__name__)


async def expand_query(query: str) -> list[str]:
    """Return [query, *up_to_2_rephrasings]."""
    prompt = (
        "Rewrite this search query in 2 different ways to help find relevant memories.\n"
        "Each rephrasing should approach the same topic from a different angle.\n"
        "Reply with exactly 2 lines, one rephrasing per line, nothing else, no numbering, "
        "no explanation.\n\n"
        f"Query: {query}\n\n"
        "Rephrasings:"
    )
    try:
        content = await ollama_provider.complete(
            [{"role": "user", "content": prompt}],
            model=MODEL_FAST,
            options={"temperature": 0.3, "num_predict": 60},
            timeout=QUERY_EXPANSION_TIMEOUT,
        )
        lines = content.strip().split("\n")
        expansions = [l.strip() for l in lines if l.strip()][:2]
        return [query] + expansions
    except Exception as e:
        logger.error("expand_query error: %s", e)
        return [query]

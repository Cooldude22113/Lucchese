"""
context/context_builder.py
Assemble the ordered context input for a single chat turn (Rule 6).

Tier 1 — profile_state (SQLite): authoritative current-truth facts, injected first.
Tier 2 — search_memory() (ChromaDB): relevant episodic/factual memory.

Failure policy: any tier that errors degrades to empty. Context assembly never
blocks a response.
"""

from __future__ import annotations

import logging

from context.context_result import ContextResult
from context.profile_context import build_tier1
from memory.retrieval.semantic_search import search_memory
from state.profile.profile_reader import get_profile_state

logger = logging.getLogger(__name__)


async def build_context(query: str) -> ContextResult:
    """Assemble Tier-1 + Tier-2 context for `query`, degrading gracefully on error."""

    # ── Tier 1: profile_state ─────────────────────────────────────────────────
    tier1_block = ""
    has_profile = False
    tier1_status = "empty_source"  # default: no row yet (expected initial state)
    tier1_error_type = ""

    try:
        profile = get_profile_state()
        if profile is not None:
            tier1_block, has_profile = build_tier1(profile)
            if has_profile:
                tier1_status = "populated"
            # else: row exists but all fields null — remains "empty_source"
        # profile is None → stays "empty_source"
    except Exception as exc:
        logger.error("build_context tier1 error: %s", exc)
        tier1_status = "failure"
        tier1_error_type = type(exc).__name__

    tier1_char_count = len(tier1_block)

    # ── Tier 2: ChromaDB memory search ────────────────────────────────────────
    tier2_block = ""
    tier2_status = "empty_source"
    tier2_error_type = ""
    tier2_result_count = 0

    try:
        tier2_block = await search_memory(query)
        if tier2_block:
            tier2_status = "populated"
            tier2_result_count = 1  # proxy: string is non-empty
    except Exception as exc:
        logger.error("build_context tier2 error: %s", exc)
        tier2_status = "failure"
        tier2_error_type = type(exc).__name__

    tier2_char_count = len(tier2_block)

    return ContextResult(
        tier1_block=tier1_block,
        tier2_block=tier2_block,
        has_profile=has_profile,
        tier1_status=tier1_status,
        tier1_error_type=tier1_error_type,
        tier1_char_count=tier1_char_count,
        tier2_status=tier2_status,
        tier2_error_type=tier2_error_type,
        tier2_char_count=tier2_char_count,
        tier2_result_count=tier2_result_count,
    )

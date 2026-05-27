# routes/context_builder.py
"""
Context assembly layer for Lucchese.

Single responsibility: build the ordered context input for the model before
each chat turn. Owns the tier priority contract — callers do not touch
context internals.

Tier 1 — profile_state (SQLite): authoritative current-truth facts.
          Always injected first. Never framed as "past conversations".
Tier 2 — search_memory() (ChromaDB): relevant episodic/factual memory.
          Injected second, unchanged from existing behaviour.

Failure policy: any tier that errors is silently degraded to an empty
string. Context assembly never blocks a response.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from routes.state import get_profile_state
from routes.memory import search_memory

logger = logging.getLogger(__name__)


# ── Data structure ─────────────────────────────────────────────────────────────

@dataclass
class ContextResult:
    """
    Internal context object produced by build_context().
    Not persisted. Not exposed via API.
    Passed directly into build_system_prompt().
    """
    tier1_block: str = ""   # Formatted current-truth string from profile_state
    tier2_block: str = ""   # Raw output of search_memory()
    has_profile: bool = False  # True if tier1 contributed any content


# Convenience: callers that need an empty context (scrape, action plan, etc.)
# can use this rather than constructing one inline.
EMPTY_CONTEXT = ContextResult()


# ── Builder ────────────────────────────────────────────────────────────────────

async def build_context(query: str) -> ContextResult:
    """
    Assemble the ordered context input for a single chat turn.

    Args:
        query: The user's current message. Used for ChromaDB retrieval.

    Returns:
        ContextResult with tier1_block and tier2_block populated where
        available. Degrades gracefully on any failure.
    """

    # ── Tier 1: profile_state ─────────────────────────────────────────────────
    tier1_block = ""
    has_profile = False

    try:
        profile = get_profile_state()
        if profile is not None:
            # Warn if profile exists but has never been confirmed through the
            # seeding flow. Values are still injected — this is a diagnostic
            # signal only, not a gate.
            if profile.get("confirmed") == 0:
                logger.warning(
                    "profile_state is unconfirmed — values may be manually written "
                    "without passing through the seeding confirmation flow"
                )

            # Parse field_meta for per-field stale_at checks.
            # Populated by seed_profile.py V2 apply mode; absent on older rows.
            field_meta: dict = {}
            raw_fm = profile.get("field_meta")
            if raw_fm:
                try:
                    field_meta = (
                        json.loads(raw_fm) if isinstance(raw_fm, str) else raw_fm
                    )
                except Exception:
                    logger.warning(
                        "build_context: field_meta JSON parse failed — stale_at checks skipped"
                    )

            now_utc = datetime.now(timezone.utc)

            def _check_stale(field_name: str) -> None:
                """Log a warning if field_meta carries a stale_at that has passed."""
                fm       = field_meta.get(field_name, {})
                stale_at = fm.get("stale_at")
                if not stale_at:
                    return
                try:
                    stale_dt = datetime.fromisoformat(stale_at)
                    if stale_dt < now_utc:
                        logger.warning(
                            "profile_state field '%s' is potentially stale "
                            "(stale_at=%s) — injecting anyway",
                            field_name,
                            stale_at,
                        )
                except Exception:
                    pass

            lines = ["CURRENT FACTS — AUTHORITATIVE:"]

            if profile.get("age") is not None:
                _check_stale("age")
                lines.append(f"Age: {profile['age']}")

            if profile.get("active_course"):
                _check_stale("active_course")
                course_line = f"Active course: {profile['active_course']}"
                if profile.get("course_status"):
                    _check_stale("course_status")
                    course_line += f" ({profile['course_status']})"
                lines.append(course_line)

            if profile.get("primary_project"):
                _check_stale("primary_project")
                lines.append(f"Primary project: {profile['primary_project']}")

            if profile.get("focus_area"):
                _check_stale("focus_area")
                lines.append(f"Current focus: {profile['focus_area']}")

            if profile.get("active_projects"):
                _check_stale("active_projects")
                lines.append(f"Active projects: {profile['active_projects']}")

            if profile.get("current_business"):
                _check_stale("current_business")
                lines.append(f"Current business: {profile['current_business']}")

            if profile.get("training_focus"):
                _check_stale("training_focus")
                lines.append(f"Training focus: {profile['training_focus']}")

            if profile.get("current_priorities"):
                _check_stale("current_priorities")
                lines.append(f"Current priorities: {profile['current_priorities']}")

            if profile.get("system_goal"):
                _check_stale("system_goal")
                lines.append(f"Lucchese system goal: {profile['system_goal']}")

            if profile.get("memory_status"):
                _check_stale("memory_status")
                lines.append(f"Memory status: {profile['memory_status']}")

            if profile.get("historical_context"):
                _check_stale("historical_context")
                lines.append(f"Historical context warning: {profile['historical_context']}")

            if profile.get("personality_mode"):
                _check_stale("personality_mode")
                lines.append(f"Preferred interaction mode: {profile['personality_mode']}")

            # Only mark has_profile if at least one real field populated
            content_lines = lines[1:]
            if content_lines:
                tier1_block = "\n".join(lines)
                has_profile = True

    except Exception as exc:
        logger.error("build_context tier1 error: %s", exc)
        # Degrade cleanly — tier1 stays empty, tier2 still runs

    # ── Tier 2: ChromaDB memory search ───────────────────────────────────────
    tier2_block = ""

    try:
        tier2_block = await search_memory(query)
    except Exception as exc:
        logger.error("build_context tier2 error: %s", exc)
        # Degrade cleanly — tier2 stays empty, tier1 still reaches model

    return ContextResult(
        tier1_block=tier1_block,
        tier2_block=tier2_block,
        has_profile=has_profile,
    )


# ── Seed reference ─────────────────────────────────────────────────────────────
# profile_state is populated via the seeding pipeline:
#
#   python seed_profile.py --extract
#   # review and edit profile_candidates.json
#   python seed_profile.py --apply
#
# Manual override (bypasses confirmation flow — will trigger the unconfirmed
# warning in build_context until confirmed=true is set):
#
# curl -X PATCH http://localhost:8000/state/profile \
#   -H "Content-Type: application/json" \
#   -d '{
#         "age": 29,
#         "active_course": "Fundamentals of Property Investment",
#         "course_status": "week 4 of 12",
#         "primary_project": "PTPreps",
#         "focus_area": "Scaling meal prep subscriptions and automating fulfilment",
#         "confirmed": true
#       }'
#
# PATCH now has merge semantics: omitted fields are preserved from the
# existing row. Partial updates are safe without reading first.
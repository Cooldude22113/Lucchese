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

    Tier status fields (added STAB-001):
      tier1_status / tier2_status — "populated" | "empty_source" | "failure" | "unknown"
        populated    — retrieval succeeded and returned non-empty content
        empty_source — retrieval succeeded but source had nothing (expected for profile_state
                       until seeded; produces INFO log only, no WARNING)
        failure      — retrieval raised an exception (produces WARNING log)
        unknown      — field was not set by build_context(); signals a missed construction
                       site during audit
      tier*_error_type — exception class name when status == "failure"; empty string otherwise
      tier1_char_count / tier2_char_count — len() of assembled block; 0 if empty or failed
      tier2_result_count — proxy for ChromaDB result count; 0 = empty, 1 = non-empty.
                           NOTE: search_memory() returns a pre-formatted string, not a list,
                           so exact result count is unavailable without a memory.py interface
                           change. This field will remain a proxy until that interface is updated.
    """
    tier1_block: str = ""   # Formatted current-truth string from profile_state
    tier2_block: str = ""   # Raw output of search_memory()
    has_profile: bool = False  # True if tier1 contributed any content

    # ── Tier status fields (STAB-001) ─────────────────────────────────────────
    tier1_status:       str = "unknown"
    tier1_error_type:   str = ""
    tier1_char_count:   int = 0

    tier2_status:       str = "unknown"
    tier2_error_type:   str = ""
    tier2_char_count:   int = 0
    tier2_result_count: int = 0


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
    tier1_block      = ""
    has_profile      = False
    tier1_status     = "empty_source"   # default: no row yet (expected initial state)
    tier1_error_type = ""

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
                tier1_block   = "\n".join(lines)
                has_profile   = True
                tier1_status  = "populated"
            # else: profile row exists but all fields null — remains "empty_source"

        # profile is None → tier1_status stays "empty_source" (expected until seeded)

    except Exception as exc:
        logger.error("build_context tier1 error: %s", exc)
        tier1_status     = "failure"
        tier1_error_type = type(exc).__name__
        # Degrade cleanly — tier1 stays empty, tier2 still runs

    tier1_char_count = len(tier1_block)

    # ── Tier 2: ChromaDB memory search ───────────────────────────────────────
    tier2_block      = ""
    tier2_status     = "empty_source"
    tier2_error_type = ""
    tier2_result_count = 0

    try:
        tier2_block = await search_memory(query)
        if tier2_block:
            tier2_status       = "populated"
            # search_memory() returns a pre-formatted string, not a list —
            # exact result count unavailable without a memory.py interface change.
            # Proxy: 1 signals non-empty; 0 signals empty. See ContextResult docstring.
            tier2_result_count = 1
        # else: tier2_status stays "empty_source", tier2_result_count stays 0
    except Exception as exc:
        logger.error("build_context tier2 error: %s", exc)
        tier2_status       = "failure"
        tier2_error_type   = type(exc).__name__
        # Degrade cleanly — tier2 stays empty, tier1 still reaches model

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


# ── Context assembly observability (STAB-001) ─────────────────────────────────

# Named logger for structured context assembly entries.
# Scope: lucchese.context only — deliberately not applied to the root logger.
# Format: each message is a pre-serialised JSON string (see emit_context_log).
_context_logger = logging.getLogger("lucchese.context")


def emit_context_log(
    context_result: "ContextResult | None",
    inference_path: str,        # "chat" or "voice"
    web_context: str,
    sheets_context: str,
) -> None:
    """
    Emit one structured INFO log entry capturing the full context assembly
    state at the point build_system_prompt() is about to be called.

    Call site: immediately before build_system_prompt() in chat.py and voice.py.

    This function must not raise. Any internal failure is suppressed so that
    a logging error can never affect inference availability.

    Log schema (one JSON object per inference):
    {
      "event":                   "context_assembly",
      "timestamp":               "<ISO 8601 UTC>",
      "inference_path":          "chat" | "voice",
      "tier1_status":            "populated" | "empty_source" | "failure" | "unknown",
      "tier1_error_type":        "<ExceptionClassName or empty string>",
      "tier1_char_count":        <int>,
      "tier2_status":            "populated" | "empty_source" | "failure" | "unknown",
      "tier2_error_type":        "<ExceptionClassName or empty string>",
      "tier2_char_count":        <int>,
      "tier2_result_count":      <int>,
      "web_context_present":     <bool>,
      "web_context_char_count":  <int>,
      "sheets_context_present":  <bool>,
      "sheets_context_char_count": <int>,
      "total_assembled_char_count": <int>,
      "context_result_present":  <bool>
    }

    Conditional WARNING entries (separate log calls):
      - event "context_tier_failure"  — when tier1_status or tier2_status == "failure"
      - event "context_assembly_null" — when context_result is None

    NOTE: Log entries contain only metadata (char counts, statuses, counts).
    Assembled context text must never appear in log entries.

    TODO (post-task): Add log rotation and retention policy before production
    deployment. Under active use, one ~400-byte JSON entry per inference will
    accumulate continuously. See STAB-001 post-task dependencies.
    """
    try:
        _now = datetime.now(timezone.utc)
        ts = _now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{_now.microsecond // 1000:03d}Z"

        web   = web_context    or ""
        sheet = sheets_context or ""

        if context_result is None:
            # Emit null WARNING, then an INFO entry with zeroed fields
            try:
                _context_logger.warning(json.dumps({
                    "event":          "context_assembly_null",
                    "timestamp":      ts,
                    "inference_path": inference_path,
                    "impact":         "model_will_proceed_with_no_assembled_context",
                }))
            except Exception:
                pass

            entry = {
                "event":                      "context_assembly",
                "timestamp":                  ts,
                "inference_path":             inference_path,
                "tier1_status":               "unknown",
                "tier1_error_type":           "",
                "tier1_char_count":           0,
                "tier2_status":               "unknown",
                "tier2_error_type":           "",
                "tier2_char_count":           0,
                "tier2_result_count":         0,
                "web_context_present":        len(web) > 0,
                "web_context_char_count":     len(web),
                "sheets_context_present":     len(sheet) > 0,
                "sheets_context_char_count":  len(sheet),
                "total_assembled_char_count": len(web) + len(sheet),
                "context_result_present":     False,
            }
            _context_logger.info(json.dumps(entry))
            return

        # ── Emit tier failure WARNINGs before the primary INFO entry ──────────
        for tier_label, status, error_type in (
            ("tier1", context_result.tier1_status, context_result.tier1_error_type),
            ("tier2", context_result.tier2_status, context_result.tier2_error_type),
        ):
            if status == "failure":
                try:
                    _context_logger.warning(json.dumps({
                        "event":          "context_tier_failure",
                        "timestamp":      ts,
                        "inference_path": inference_path,
                        "tier":           tier_label,
                        "error_type":     error_type,
                        "impact":         "model_will_proceed_without_tier",
                    }))
                except Exception:
                    pass

        # ── Primary INFO entry ────────────────────────────────────────────────
        total = (
            context_result.tier1_char_count
            + context_result.tier2_char_count
            + len(web)
            + len(sheet)
        )
        entry = {
            "event":                      "context_assembly",
            "timestamp":                  ts,
            "inference_path":             inference_path,
            "tier1_status":               context_result.tier1_status,
            "tier1_error_type":           context_result.tier1_error_type,
            "tier1_char_count":           context_result.tier1_char_count,
            "tier2_status":               context_result.tier2_status,
            "tier2_error_type":           context_result.tier2_error_type,
            "tier2_char_count":           context_result.tier2_char_count,
            "tier2_result_count":         context_result.tier2_result_count,
            "web_context_present":        len(web) > 0,
            "web_context_char_count":     len(web),
            "sheets_context_present":     len(sheet) > 0,
            "sheets_context_char_count":  len(sheet),
            "total_assembled_char_count": total,
            "context_result_present":     True,
        }
        _context_logger.info(json.dumps(entry))

    except Exception:
        # Logging must never surface to the caller.
        # Inference continues regardless.
        pass


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
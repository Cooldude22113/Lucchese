"""
context/profile_context.py
Format the profile_state row into the Tier-1 "current facts" context block (Rule 6).

Owns the field ordering, the per-field stale_at check (warning-only), and the
unconfirmed-profile warning. Returns the assembled block plus whether any content
was contributed.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# (profile key, label) in injection order. Some fields compose (see build_tier1).
_SIMPLE_FIELDS: list[tuple[str, str]] = [
    ("primary_project", "Primary project"),
    ("focus_area", "Current focus"),
    ("active_projects", "Active projects"),
    ("current_business", "Current business"),
    ("training_focus", "Training focus"),
    ("current_priorities", "Current priorities"),
    ("system_goal", "Lucchese system goal"),
    ("memory_status", "Memory status"),
    ("historical_context", "Historical context warning"),
    ("personality_mode", "Preferred interaction mode"),
]


def build_tier1(profile: dict) -> tuple[str, bool]:
    """
    Build the Tier-1 block from a profile_state dict.
    Returns (block, has_profile). has_profile is True only if at least one real
    field was populated.
    """
    if profile.get("confirmed") == 0:
        logger.warning(
            "profile_state is unconfirmed — values may be manually written "
            "without passing through the seeding confirmation flow"
        )

    # Parse field_meta for per-field stale_at checks (absent on older rows).
    field_meta: dict = {}
    raw_fm = profile.get("field_meta")
    if raw_fm:
        try:
            field_meta = json.loads(raw_fm) if isinstance(raw_fm, str) else raw_fm
        except Exception:
            logger.warning(
                "build_context: field_meta JSON parse failed — stale_at checks skipped"
            )

    now_utc = datetime.now(timezone.utc)

    def _check_stale(field_name: str) -> None:
        fm = field_meta.get(field_name, {})
        stale_at = fm.get("stale_at")
        if not stale_at:
            return
        try:
            stale_dt = datetime.fromisoformat(stale_at)
            if stale_dt < now_utc:
                logger.warning(
                    "profile_state field '%s' is potentially stale (stale_at=%s) — injecting anyway",
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

    for key, label in _SIMPLE_FIELDS:
        if profile.get(key):
            _check_stale(key)
            lines.append(f"{label}: {profile[key]}")

    content_lines = lines[1:]
    if content_lines:
        return "\n".join(lines), True
    return "", False

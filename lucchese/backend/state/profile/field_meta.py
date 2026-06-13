"""
state/profile/field_meta.py
Field-level provenance merging for profile_state (Rule 10: testable domain logic,
no framework dependency).

profile_state.field_meta is a JSON blob of per-field metadata (e.g. stale_at).
Updates must merge at the field level — incoming keys overwrite, existing keys not
present in the incoming payload are preserved — never blob-replace.
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)

# Fields that may be explicitly nulled via a clear request.
CLEARABLE: set[str] = {
    "age", "active_course", "course_status", "primary_project",
    "focus_area", "active_projects", "current_business", "training_focus",
    "current_priorities", "historical_context",
}


def merge_field_meta(existing_json: str | None, incoming: dict | None) -> str | None:
    """
    Merge field_meta at the field level. Returns a serialised JSON string, or None
    if the result is empty. Corrupt existing JSON is logged and reset to empty.
    """
    if not existing_json:
        existing: dict = {}
    else:
        try:
            existing = json.loads(existing_json)
        except Exception:
            log.warning("merge_field_meta: field_meta JSON corrupt in DB — resetting to empty")
            existing = {}

    if incoming is None:
        return json.dumps(existing) if existing else None

    merged = {**existing, **incoming}
    return json.dumps(merged) if merged else None

"""
state/profile/profile_writer.py
Merge-write of the single profile_state row (Rule 9 + Rule 10).

PATCH semantics: incoming non-null fields win, omitted fields are preserved from
the existing row (no clobbering). field_meta merges at the field level. Named
fields can be explicitly nulled via clear_fields. Kept framework-free — the route
maps its request model to plain values before calling here.
"""

from __future__ import annotations

from datetime import datetime, timezone

from state.profile.field_meta import CLEARABLE, merge_field_meta
from storage.sqlite.connection import state_session

# profile_state columns this writer merges (excludes id/confirmed/field_meta/updated_at).
_MERGE_COLUMNS: tuple[str, ...] = (
    "age", "active_course", "course_status", "primary_project", "focus_area",
    "active_projects", "current_business", "training_focus",
    "current_priorities", "historical_context",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_profile(
    values: dict,
    *,
    field_meta: dict | None = None,
    confirmed: bool | None = None,
    clear_fields: list[str] | None = None,
) -> dict:
    """
    Merge `values` (column -> value | None) over the existing row and write back.

    - A None value means "preserve existing".
    - confirmed=None preserves the existing flag.
    - field_meta merges field-by-field.
    - clear_fields explicitly nulls named (clearable) columns after the merge.
    """
    clear_fields = clear_fields or []

    with state_session() as conn:
        row = conn.execute("SELECT * FROM profile_state WHERE id=1").fetchone()
        existing: dict = dict(row) if row is not None else {}

        # COALESCE: incoming wins if not None, else keep existing.
        merged: dict = {
            col: (values.get(col) if values.get(col) is not None else existing.get(col))
            for col in _MERGE_COLUMNS
        }

        if confirmed is not None:
            merged_confirmed = 1 if confirmed else 0
        else:
            merged_confirmed = existing.get("confirmed", 0)

        merged_field_meta = merge_field_meta(existing.get("field_meta"), field_meta)

        # Explicit clears — null named clearable fields.
        for fname in clear_fields:
            if fname in CLEARABLE and fname in merged:
                merged[fname] = None

        conn.execute(
            """
            INSERT OR REPLACE INTO profile_state
                (id, age, active_course, course_status, primary_project, focus_area,
                 active_projects, current_business, training_focus, current_priorities,
                 historical_context, confirmed, field_meta, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                merged["age"],
                merged["active_course"],
                merged["course_status"],
                merged["primary_project"],
                merged["focus_area"],
                merged["active_projects"],
                merged["current_business"],
                merged["training_focus"],
                merged["current_priorities"],
                merged["historical_context"],
                merged_confirmed,
                merged_field_meta,
                _now(),
            ),
        )

    return {"status": "ok"}

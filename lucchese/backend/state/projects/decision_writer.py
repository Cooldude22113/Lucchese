"""
state/projects/decision_writer.py
Record decisions against a project in the state database (Rule 9).
"""

from __future__ import annotations

from datetime import datetime, timezone

from storage.sqlite.connection import state_session


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_decision(project_id: int | None, decision: str, reason: str | None) -> int:
    """Insert a decision; returns the new row id."""
    with state_session() as conn:
        cur = conn.execute(
            "INSERT INTO decisions (project_id, decision, reason, created_at) "
            "VALUES (?, ?, ?, ?)",
            (project_id, decision, reason, _now()),
        )
    return cur.lastrowid

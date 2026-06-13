"""
state/projects/blocker_writer.py
Create and resolve blockers in the state database (Rule 9).

resolve_blocker returns whether a row was updated; the route turns False into 404.
"""

from __future__ import annotations

from datetime import datetime, timezone

from storage.sqlite.connection import state_session


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_blocker(project_id: int | None, blocker: str) -> int:
    """Insert a blocker; returns the new row id."""
    with state_session() as conn:
        cur = conn.execute(
            "INSERT INTO blockers (project_id, blocker, created_at) VALUES (?, ?, ?)",
            (project_id, blocker, _now()),
        )
    return cur.lastrowid


def resolve_blocker(blocker_id: int) -> bool:
    """Mark a blocker resolved. Returns True if it existed, False otherwise."""
    with state_session() as conn:
        cur = conn.execute(
            "UPDATE blockers SET status='resolved', resolved_at=? WHERE id=?",
            (_now(), blocker_id),
        )
    return cur.rowcount > 0

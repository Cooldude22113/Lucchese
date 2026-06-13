"""
state/projects/project_writer.py
Create projects in the state database (Rule 9).
"""

from __future__ import annotations

from datetime import datetime, timezone

from storage.sqlite.connection import state_session


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_project(name: str, current_focus: str | None, next_action: str | None) -> int:
    """Insert a project; returns the new row id."""
    t = _now()
    with state_session() as conn:
        cur = conn.execute(
            "INSERT INTO projects (name, current_focus, next_action, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, current_focus, next_action, t, t),
        )
    return cur.lastrowid

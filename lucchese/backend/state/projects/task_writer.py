"""
state/projects/task_writer.py
Create and complete tasks in the state database (Rule 9).

complete_task returns whether a row was updated; the route layer turns a False
into a 404 so this module stays free of HTTP/framework concerns (Rule 21).
"""

from __future__ import annotations

from datetime import datetime, timezone

from storage.sqlite.connection import state_session


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_task(
    project_id: int | None,
    title: str,
    priority: str,
    notes: str | None,
) -> int:
    """Insert a task; returns the new row id."""
    t = _now()
    with state_session() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (project_id, title, priority, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, title, priority, notes, t, t),
        )
    return cur.lastrowid


def complete_task(task_id: int) -> bool:
    """Mark a task done. Returns True if the task existed, False otherwise."""
    with state_session() as conn:
        cur = conn.execute(
            "UPDATE tasks SET status='done', updated_at=? WHERE id=?",
            (_now(), task_id),
        )
    return cur.rowcount > 0

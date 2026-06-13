"""
state/projects/project_reader.py
Read surface for the project tracker (Rule 9 mechanics via storage).
"""

from __future__ import annotations

from storage.sqlite.connection import state_session


def overview() -> dict:
    """Projects plus open tasks, open blockers, and recent decisions."""
    with state_session() as conn:
        projects = conn.execute(
            "SELECT * FROM projects ORDER BY updated_at DESC"
        ).fetchall()
        tasks = conn.execute(
            "SELECT * FROM tasks WHERE status='open' ORDER BY id DESC LIMIT 20"
        ).fetchall()
        blockers = conn.execute(
            "SELECT * FROM blockers WHERE status='open' ORDER BY id DESC"
        ).fetchall()
        decisions = conn.execute(
            "SELECT * FROM decisions ORDER BY id DESC LIMIT 10"
        ).fetchall()

    return {
        "projects": [dict(r) for r in projects],
        "open_tasks": [dict(r) for r in tasks],
        "open_blockers": [dict(r) for r in blockers],
        "recent_decisions": [dict(r) for r in decisions],
    }

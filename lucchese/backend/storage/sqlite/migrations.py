"""
storage/sqlite/migrations.py
Idempotent SQLite column migrations (Rule 9).

Currently only the state database needs migrations: older profile_state rows
pre-date the active_projects/current_business/training_focus/current_priorities/
historical_context columns and the confirmed/field_meta columns. Each ALTER is
skipped if the column already exists.
"""

from __future__ import annotations

import logging
import sqlite3

log = logging.getLogger(__name__)

# column name -> SQL type, added to profile_state if missing.
_PROFILE_STATE_NEW_COLUMNS: dict[str, str] = {
    "active_projects": "TEXT",
    "current_business": "TEXT",
    "training_focus": "TEXT",
    "current_priorities": "TEXT",
    "historical_context": "TEXT",
    "confirmed": "INTEGER NOT NULL DEFAULT 0",
    "field_meta": "TEXT",
}


def apply_state_migrations(conn: sqlite3.Connection) -> None:
    """
    Bring an existing profile_state table up to the current column set.
    Raises on PRAGMA failure — a broken database should not start silently.
    """
    try:
        rows = conn.execute("PRAGMA table_info(profile_state)").fetchall()
    except Exception as e:
        log.error("apply_state_migrations: PRAGMA table_info(profile_state) failed: %s", e)
        raise

    existing = {row["name"] for row in rows}
    for name, col_def in _PROFILE_STATE_NEW_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE profile_state ADD COLUMN {name} {col_def}")
            log.info("apply_state_migrations: added column '%s' to profile_state", name)

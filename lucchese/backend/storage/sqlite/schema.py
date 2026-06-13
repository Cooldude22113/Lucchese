"""
storage/sqlite/schema.py
Canonical SQLite schema for both databases (Rule 9).

This is the single source of truth for table structure. init_conversations_db() and
init_state_db() create the tables; the EXPECTED_* catalogues expose the same truth
as data so observability/startup_validator.py can validate a live DB without
re-declaring column lists (the validator previously hardcoded its own catalogue).
"""

from __future__ import annotations

import sqlite3

from config.paths import CONVERSATIONS_DB, STATE_DB
from storage.sqlite.connection import connect
from storage.sqlite import migrations

# ── conversations.db DDL ──────────────────────────────────────────────────────
_CONVERSATIONS_DDL = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    title       TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE INDEX IF NOT EXISTS idx_messages_conv_id ON messages(conversation_id);

CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    file_type   TEXT NOT NULL,
    chunk_count INTEGER NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS roleplay_sessions (
    conversation_id TEXT PRIMARY KEY,
    exchanges       INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);
"""

# ── lucchese_state.db DDL ─────────────────────────────────────────────────────
_STATE_DDL = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active',
    current_focus TEXT,
    next_action TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    priority TEXT NOT NULL DEFAULT 'medium',
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    decision TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS blockers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    blocker TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS daily_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    active_project TEXT,
    active_mode TEXT,
    current_focus TEXT,
    last_summary TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS profile_state (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    age              INTEGER,
    active_course    TEXT,
    course_status    TEXT,
    primary_project  TEXT,
    active_projects     TEXT,
    current_business    TEXT,
    training_focus      TEXT,
    current_priorities  TEXT,
    historical_context  TEXT,
    focus_area       TEXT,
    confirmed        INTEGER NOT NULL DEFAULT 0,
    field_meta       TEXT,
    updated_at       TEXT NOT NULL
);
"""

# ── Structured catalogue for startup validation ───────────────────────────────
# Maps database path -> {table_name: [expected column names]}. Keep in lockstep
# with the DDL above. observability/startup_validator.py imports these.
EXPECTED_CONVERSATIONS_TABLES: dict[str, list[str]] = {
    "conversations": ["id", "created_at", "updated_at", "title"],
    "messages": ["id", "conversation_id", "role", "content", "created_at"],
    "documents": ["id", "filename", "file_type", "chunk_count", "created_at"],
    "roleplay_sessions": ["conversation_id", "exchanges", "created_at"],
}

EXPECTED_STATE_TABLES: dict[str, list[str]] = {
    "projects": ["id", "name", "status", "current_focus", "next_action", "created_at", "updated_at"],
    "tasks": ["id", "project_id", "title", "status", "priority", "notes", "created_at", "updated_at"],
    "decisions": ["id", "project_id", "decision", "reason", "created_at"],
    "blockers": ["id", "project_id", "blocker", "status", "created_at", "resolved_at"],
    "daily_state": ["id", "active_project", "active_mode", "current_focus", "last_summary", "updated_at"],
    "profile_state": [
        "id", "age", "active_course", "course_status", "primary_project",
        "active_projects", "current_business", "training_focus", "current_priorities",
        "historical_context", "focus_area", "confirmed", "field_meta", "updated_at",
    ],
}


def init_conversations_db() -> None:
    """Create the conversations database schema if absent. Idempotent."""
    con = connect(CONVERSATIONS_DB)
    try:
        con.executescript(_CONVERSATIONS_DDL)
        con.commit()
    finally:
        con.close()


def init_state_db() -> None:
    """Create the state database schema, then apply column migrations. Idempotent."""
    con = connect(STATE_DB)
    try:
        con.executescript(_STATE_DDL)
        migrations.apply_state_migrations(con)
        con.commit()
    finally:
        con.close()

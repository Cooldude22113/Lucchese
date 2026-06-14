"""
storage/sqlite/conversation_store_schema.py
Canonical SQLite schema for the imported-conversation store (Rule 9).

This is the single source of truth for the universal conversation shape that holds
ChatGPT, Grok, and (later) Lucchese conversations under integer primary keys. It
mirrors the dataclasses in ingestion/parsing/normalized_models.py field-for-field.

Kept deliberately separate from storage/sqlite/schema.py: that file owns the live
TEXT-id conversations.db; this file owns conversation_store.db (CONVERSATION_STORE_DB),
so the integer-id canonical tables never collide with the live tables. At migration
time this becomes the single conversation store.

init_conversation_store_db() creates the tables; EXPECTED_STORE_TABLES exposes the
same truth as data for observability/startup_validator.py, matching the schema.py
pattern.
"""

from __future__ import annotations

from config.paths import CONVERSATION_STORE_DB
from storage.sqlite.connection import connect

# ── conversation_store.db DDL ─────────────────────────────────────────────────
_STORE_DDL = """
CREATE TABLE IF NOT EXISTS conversations (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    source                 TEXT NOT NULL,
    source_conversation_id TEXT NOT NULL,
    title                  TEXT,
    summary                TEXT,
    created_at             TEXT,
    updated_at             TEXT,
    default_model          TEXT,
    system_prompt_name     TEXT,
    starred                INTEGER NOT NULL DEFAULT 0,
    archived               INTEGER NOT NULL DEFAULT 0,
    message_count          INTEGER NOT NULL DEFAULT 0,
    source_metadata        TEXT,
    imported_at            TEXT NOT NULL,
    UNIQUE(source, source_conversation_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id   INTEGER NOT NULL,
    source_message_id TEXT NOT NULL,
    parent_id         INTEGER,
    role              TEXT NOT NULL,
    author_name       TEXT,
    content_type      TEXT,
    text              TEXT,
    raw_text          TEXT,
    model             TEXT,
    recipient         TEXT,
    status            TEXT,
    end_turn          INTEGER,
    weight            REAL,
    sequence          INTEGER,
    on_active_path    INTEGER NOT NULL DEFAULT 1,
    is_hidden         INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT,
    updated_at        TEXT,
    source_metadata   TEXT,
    UNIQUE(conversation_id, source_message_id),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    FOREIGN KEY (parent_id) REFERENCES messages(id)
);

CREATE INDEX IF NOT EXISTS idx_store_messages_conv ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_store_messages_parent ON messages(parent_id);

CREATE TABLE IF NOT EXISTS tool_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    message_id      INTEGER NOT NULL,
    source          TEXT NOT NULL,
    tool_name       TEXT,
    command         TEXT,
    arguments       TEXT,
    created_at      TEXT,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    FOREIGN KEY (message_id) REFERENCES messages(id)
);

CREATE TABLE IF NOT EXISTS web_searches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    message_id      INTEGER NOT NULL,
    source          TEXT NOT NULL,
    query           TEXT,
    num_results     INTEGER,
    search_source   TEXT,
    created_at      TEXT,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    FOREIGN KEY (message_id) REFERENCES messages(id)
);

CREATE TABLE IF NOT EXISTS search_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    message_id      INTEGER NOT NULL,
    web_search_id   INTEGER,
    source          TEXT NOT NULL,
    kind            TEXT,
    url             TEXT,
    domain          TEXT,
    title           TEXT,
    snippet         TEXT,
    pub_date        TEXT,
    rank            INTEGER,
    created_at      TEXT,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    FOREIGN KEY (message_id) REFERENCES messages(id),
    FOREIGN KEY (web_search_id) REFERENCES web_searches(id)
);

CREATE INDEX IF NOT EXISTS idx_store_search_results_domain ON search_results(domain);

CREATE TABLE IF NOT EXISTS attachments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    message_id      INTEGER NOT NULL,
    source          TEXT NOT NULL,
    kind            TEXT,
    source_asset_id TEXT,
    name            TEXT,
    mime_type       TEXT,
    url             TEXT,
    size            INTEGER,
    width           INTEGER,
    height          INTEGER,
    created_at      TEXT,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    FOREIGN KEY (message_id) REFERENCES messages(id)
);

CREATE TABLE IF NOT EXISTS reasoning_traces (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    message_id      INTEGER NOT NULL,
    source          TEXT NOT NULL,
    kind            TEXT,
    content         TEXT,
    started_at      TEXT,
    ended_at        TEXT,
    seq             INTEGER,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    FOREIGN KEY (message_id) REFERENCES messages(id)
);

CREATE TABLE IF NOT EXISTS id_map (
    source      TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    source_id   TEXT NOT NULL,
    new_id      INTEGER NOT NULL,
    PRIMARY KEY (source, entity_type, source_id)
);

CREATE TABLE IF NOT EXISTS import_runs (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    source                 TEXT NOT NULL,
    started_at             TEXT NOT NULL,
    finished_at            TEXT,
    files                  TEXT,
    conversations_imported INTEGER NOT NULL DEFAULT 0,
    messages_imported      INTEGER NOT NULL DEFAULT 0,
    errors                 INTEGER NOT NULL DEFAULT 0,
    report                 TEXT
);
"""

# ── Structured catalogue for startup validation ───────────────────────────────
# Keep in lockstep with the DDL above (mirrors schema.EXPECTED_* convention).
EXPECTED_STORE_TABLES: dict[str, list[str]] = {
    "conversations": [
        "id", "source", "source_conversation_id", "title", "summary",
        "created_at", "updated_at", "default_model", "system_prompt_name",
        "starred", "archived", "message_count", "source_metadata", "imported_at",
    ],
    "messages": [
        "id", "conversation_id", "source_message_id", "parent_id", "role",
        "author_name", "content_type", "text", "raw_text", "model", "recipient",
        "status", "end_turn", "weight", "sequence", "on_active_path", "is_hidden",
        "created_at", "updated_at", "source_metadata",
    ],
    "tool_calls": [
        "id", "conversation_id", "message_id", "source", "tool_name", "command",
        "arguments", "created_at",
    ],
    "web_searches": [
        "id", "conversation_id", "message_id", "source", "query", "num_results",
        "search_source", "created_at",
    ],
    "search_results": [
        "id", "conversation_id", "message_id", "web_search_id", "source", "kind",
        "url", "domain", "title", "snippet", "pub_date", "rank", "created_at",
    ],
    "attachments": [
        "id", "conversation_id", "message_id", "source", "kind", "source_asset_id",
        "name", "mime_type", "url", "size", "width", "height", "created_at",
    ],
    "reasoning_traces": [
        "id", "conversation_id", "message_id", "source", "kind", "content",
        "started_at", "ended_at", "seq",
    ],
    "id_map": ["source", "entity_type", "source_id", "new_id"],
    "import_runs": [
        "id", "source", "started_at", "finished_at", "files",
        "conversations_imported", "messages_imported", "errors", "report",
    ],
}


def init_conversation_store_db() -> None:
    """Create the canonical conversation store schema if absent. Idempotent."""
    con = connect(CONVERSATION_STORE_DB)
    try:
        con.executescript(_STORE_DDL)
        con.commit()
    finally:
        con.close()

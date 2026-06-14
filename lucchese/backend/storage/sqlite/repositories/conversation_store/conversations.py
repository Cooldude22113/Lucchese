"""
storage/sqlite/repositories/conversation_store/conversations.py
Conversation rows in the canonical store (Rule 9, Rule 22, Rule 23).

Write helpers take an open connection so the pipeline can persist a whole
conversation (conversation + messages + behavioural rows + parent resolution) in a
single transaction. Read helpers open their own session for the status endpoint.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from config.paths import CONVERSATION_STORE_DB
from storage.sqlite.connection import session

_INSERT = """
INSERT INTO conversations (
    source, source_conversation_id, title, summary, created_at, updated_at,
    default_model, system_prompt_name, starred, archived, message_count,
    source_metadata, imported_at
) VALUES (
    :source, :source_conversation_id, :title, :summary, :created_at, :updated_at,
    :default_model, :system_prompt_name, :starred, :archived, :message_count,
    :source_metadata, :imported_at
)
"""


def insert(con: sqlite3.Connection, row: dict) -> int:
    """Insert one conversation; return the assigned integer id."""
    params = {
        "source": row["source"],
        "source_conversation_id": row["source_conversation_id"],
        "title": row.get("title"),
        "summary": row.get("summary"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "default_model": row.get("default_model"),
        "system_prompt_name": row.get("system_prompt_name"),
        "starred": 1 if row.get("starred") else 0,
        "archived": 1 if row.get("archived") else 0,
        "message_count": row.get("message_count", 0),
        "source_metadata": row.get("source_metadata"),
        "imported_at": row.get("imported_at") or datetime.now(timezone.utc).isoformat(),
    }
    cur = con.execute(_INSERT, params)
    return int(cur.lastrowid)


def exists(con: sqlite3.Connection, source: str, source_conversation_id: str) -> int | None:
    """Return the existing integer id for this source conversation, or None."""
    row = con.execute(
        "SELECT id FROM conversations WHERE source = ? AND source_conversation_id = ?",
        (source, source_conversation_id),
    ).fetchone()
    return int(row["id"]) if row else None


def update_message_count(con: sqlite3.Connection, conversation_id: int, count: int) -> None:
    """Set the cached message_count after all messages are inserted."""
    con.execute(
        "UPDATE conversations SET message_count = ? WHERE id = ?",
        (count, conversation_id),
    )


def existing_source_ids(source: str) -> set[str]:
    """Return the set of already-imported source_conversation_id for a source.

    Loaded once per run so the import pipeline can skip in-memory (idempotency)
    without a round-trip per conversation.
    """
    with session(CONVERSATION_STORE_DB) as con:
        rows = con.execute(
            "SELECT source_conversation_id FROM conversations WHERE source = ?",
            (source,),
        ).fetchall()
    return {r["source_conversation_id"] for r in rows}


def count_by_source() -> dict[str, int]:
    """Status helper: conversation counts grouped by source."""
    with session(CONVERSATION_STORE_DB) as con:
        rows = con.execute(
            "SELECT source, COUNT(*) AS n FROM conversations GROUP BY source"
        ).fetchall()
    return {r["source"]: int(r["n"]) for r in rows}

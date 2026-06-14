"""
storage/sqlite/repositories/conversation_store/messages.py
Message rows in the canonical store (Rule 9, Rule 22, Rule 23).

Messages are inserted without parent_id first (the old parent id is not yet
resolved to an integer); resolve_parent() sets it afterwards from the id_map.
"""

from __future__ import annotations

import sqlite3

from config.paths import CONVERSATION_STORE_DB
from storage.sqlite.connection import session

_INSERT = """
INSERT INTO messages (
    conversation_id, source_message_id, parent_id, role, author_name,
    content_type, text, raw_text, model, recipient, status, end_turn, weight,
    sequence, on_active_path, is_hidden, created_at, updated_at, source_metadata
) VALUES (
    :conversation_id, :source_message_id, :parent_id, :role, :author_name,
    :content_type, :text, :raw_text, :model, :recipient, :status, :end_turn, :weight,
    :sequence, :on_active_path, :is_hidden, :created_at, :updated_at, :source_metadata
)
"""


def insert(con: sqlite3.Connection, row: dict) -> int:
    """Insert one message (parent_id left NULL); return the assigned integer id."""
    params = {
        "conversation_id": row["conversation_id"],
        "source_message_id": row["source_message_id"],
        "parent_id": row.get("parent_id"),
        "role": row.get("role"),
        "author_name": row.get("author_name"),
        "content_type": row.get("content_type"),
        "text": row.get("text"),
        "raw_text": row.get("raw_text"),
        "model": row.get("model"),
        "recipient": row.get("recipient"),
        "status": row.get("status"),
        "end_turn": _as_int_or_none(row.get("end_turn")),
        "weight": row.get("weight"),
        "sequence": row.get("sequence"),
        "on_active_path": 1 if row.get("on_active_path") else 0,
        "is_hidden": 1 if row.get("is_hidden") else 0,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "source_metadata": row.get("source_metadata"),
    }
    cur = con.execute(_INSERT, params)
    return int(cur.lastrowid)


def resolve_parent(con: sqlite3.Connection, message_id: int, parent_id: int) -> None:
    """Set the resolved integer parent_id for a message."""
    con.execute(
        "UPDATE messages SET parent_id = ? WHERE id = ?",
        (parent_id, message_id),
    )


def count_by_role() -> dict[str, int]:
    """Status helper: message counts grouped by role."""
    with session(CONVERSATION_STORE_DB) as con:
        rows = con.execute(
            "SELECT role, COUNT(*) AS n FROM messages GROUP BY role"
        ).fetchall()
    return {r["role"]: int(r["n"]) for r in rows}


def _as_int_or_none(value) -> int | None:
    if value is None:
        return None
    return 1 if value else 0

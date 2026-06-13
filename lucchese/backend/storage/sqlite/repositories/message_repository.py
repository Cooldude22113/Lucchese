"""
storage/sqlite/repositories/message_repository.py
Message persistence for the conversations database (Rule 9, Rule 22).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from storage.sqlite.connection import get_con


def save_message(conversation_id: str, role: str, content: str) -> None:
    """
    Insert a message, upserting the parent conversation row and refreshing its
    title from the first user message. Best-effort: rolls back and logs on error.
    """
    now = datetime.now(timezone.utc).isoformat()
    con = get_con()
    cur = con.cursor()
    try:
        cur.execute(
            """
            INSERT INTO conversations (id, created_at, updated_at, title)
            VALUES (?, ?, ?, NULL)
            ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (conversation_id, now, now),
        )
        cur.execute(
            "INSERT INTO messages (id, conversation_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), conversation_id, role, content, now),
        )
        cur.execute(
            """
            UPDATE conversations SET title = (
                SELECT substr(content, 1, 60) || CASE WHEN length(content) > 60 THEN '...' ELSE '' END
                FROM messages WHERE conversation_id = ? AND role = 'user'
                ORDER BY created_at LIMIT 1
            ) WHERE id = ?
            """,
            (conversation_id, conversation_id),
        )
        con.commit()
    except Exception as e:
        print(f"save_message error: {e}")
        con.rollback()
    finally:
        con.close()


def get_conversation_history(conversation_id: str, limit: int = 20) -> list[dict]:
    """Return the last N messages for a conversation, oldest first."""
    con = get_con()
    rows = con.execute(
        "SELECT role, content FROM messages WHERE conversation_id = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (conversation_id, limit),
    ).fetchall()
    con.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

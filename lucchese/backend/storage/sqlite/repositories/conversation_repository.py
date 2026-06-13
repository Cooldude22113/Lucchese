"""
storage/sqlite/repositories/conversation_repository.py
Conversation listing/reading/deletion for the conversations database (Rule 9).
"""

from __future__ import annotations

from storage.sqlite.connection import get_con


def list_conversations() -> list[dict]:
    """All conversations, most recently updated first."""
    con = get_con()
    rows = con.execute(
        "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def get_conversation(conversation_id: str) -> list[dict]:
    """All messages in a conversation, oldest first."""
    con = get_con()
    rows = con.execute(
        "SELECT role, content, created_at FROM messages WHERE conversation_id = ? "
        "ORDER BY created_at",
        (conversation_id,),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def delete_conversation_messages(conversation_id: str) -> None:
    """Delete all messages and the conversation record from SQLite."""
    con = get_con()
    con.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
    con.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    con.commit()
    con.close()

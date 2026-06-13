"""
storage/sqlite/repositories/roleplay_repository.py
Roleplay session persistence for the conversations database (Rule 9).

Pure storage of the per-conversation exchange counter. The roleplay behaviour
(Carol persona, feedback) lives in business_logic/roleplay/.
"""

from __future__ import annotations

from datetime import datetime, timezone

from storage.sqlite.connection import get_con


def get_roleplay_session(conversation_id: str) -> dict | None:
    con = get_con()
    row = con.execute(
        "SELECT exchanges FROM roleplay_sessions WHERE conversation_id = ?",
        (conversation_id,),
    ).fetchone()
    con.close()
    return {"exchanges": row["exchanges"]} if row else None


def upsert_roleplay_session(conversation_id: str, exchanges: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    con = get_con()
    con.execute(
        """
        INSERT INTO roleplay_sessions (conversation_id, exchanges, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(conversation_id) DO UPDATE SET exchanges = excluded.exchanges
        """,
        (conversation_id, exchanges, now),
    )
    con.commit()
    con.close()


def delete_roleplay_session(conversation_id: str) -> dict:
    """Delete the session and return its last-known state (or {} if absent)."""
    session = get_roleplay_session(conversation_id)
    con = get_con()
    con.execute(
        "DELETE FROM roleplay_sessions WHERE conversation_id = ?",
        (conversation_id,),
    )
    con.commit()
    con.close()
    return session or {}

"""
application/services/conversation_service.py
Reusable conversation actions (Rule 4).

Delete coordinates two systems — ChromaDB memory purge and SQLite record deletion
(Rule 3) — behind one action.
"""

from __future__ import annotations

from memory.inspection.memory_delete import purge_conversation
from storage.sqlite.repositories.conversation_repository import (
    delete_conversation_messages,
    get_conversation,
    list_conversations,
)


def list_all() -> list[dict]:
    return list_conversations()


def get(conversation_id: str) -> list[dict]:
    return get_conversation(conversation_id)


def delete(conversation_id: str) -> dict:
    """Purge associated memory (best-effort) then delete the SQLite records."""
    purge_conversation(conversation_id)          # Phase 1 — ChromaDB
    delete_conversation_messages(conversation_id)  # Phase 2 — SQLite
    return {"deleted": conversation_id}

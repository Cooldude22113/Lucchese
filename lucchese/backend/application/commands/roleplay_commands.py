"""
application/commands/roleplay_commands.py
Decide whether the chat flow should route a message to the roleplay runner (Rule 4).

A message is handled by roleplay if it starts a new roleplay OR a session is already
active for the conversation.
"""

from __future__ import annotations

from business_logic.roleplay.roleplay_detection import is_start_phrase
from business_logic.roleplay.roleplay_state import (
    get_roleplay_session,
    upsert_roleplay_session,
)


def should_handle_roleplay(message: str, conversation_id: str) -> bool:
    """True if this message belongs to a (new or active) roleplay session."""
    is_active = get_roleplay_session(conversation_id) is not None
    return is_start_phrase(message) or is_active


def ensure_session_started(message: str, conversation_id: str) -> None:
    """Open a session when a start phrase begins a brand-new roleplay."""
    is_active = get_roleplay_session(conversation_id) is not None
    if is_start_phrase(message) and not is_active:
        upsert_roleplay_session(conversation_id, 0)

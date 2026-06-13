"""
business_logic/roleplay/roleplay_state.py
Roleplay session state access (Rule 10 over Rule 9 storage).

Thin domain wrapper over the roleplay repository so the runner and chat command
layer depend on roleplay concepts, not raw SQLite.
"""

from __future__ import annotations

from storage.sqlite.repositories.roleplay_repository import (
    delete_roleplay_session,
    get_roleplay_session,
    upsert_roleplay_session,
)

__all__ = [
    "get_roleplay_session",
    "upsert_roleplay_session",
    "delete_roleplay_session",
]

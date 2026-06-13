"""
state/profile/profile_reader.py
Read access to the single profile_state row (Rule 9 mechanics via storage;
this is the state purpose-system's read surface).
"""

from __future__ import annotations

from storage.sqlite.connection import state_session


def get_profile_state() -> dict | None:
    """
    Return the profile_state row as a dict, or None if it has never been written.
    Consumed by context assembly (tier 1 current-truth facts).
    """
    with state_session() as conn:
        row = conn.execute("SELECT * FROM profile_state WHERE id=1").fetchone()
        return dict(row) if row else None


def get_profile() -> dict:
    """Like get_profile_state() but returns {} instead of None (API GET shape)."""
    return get_profile_state() or {}

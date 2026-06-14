"""
storage/sqlite/repositories/conversation_store/id_map.py
Old-id → new-integer-id mapping for the canonical store (Rule 9, Rule 23).

This is the "paired by old id" mechanism: every conversation and message records
(source, entity_type, source_id) → new_id so that parent/child links expressed in
the original UUIDs can be re-resolved to the new integer ids after insert, and so
re-running an import can detect what already exists (idempotency).
"""

from __future__ import annotations

import sqlite3

_INSERT = """
INSERT OR REPLACE INTO id_map (source, entity_type, source_id, new_id)
VALUES (?, ?, ?, ?)
"""


def record(
    con: sqlite3.Connection,
    source: str,
    entity_type: str,
    source_id: str,
    new_id: int,
) -> None:
    """Record an old-id → new-id pairing (entity_type: 'conversation'|'message')."""
    con.execute(_INSERT, (source, entity_type, source_id, new_id))


def lookup(
    con: sqlite3.Connection,
    source: str,
    entity_type: str,
    source_id: str,
) -> int | None:
    """Resolve an old id to its new integer id, or None if unknown."""
    row = con.execute(
        "SELECT new_id FROM id_map WHERE source = ? AND entity_type = ? AND source_id = ?",
        (source, entity_type, source_id),
    ).fetchone()
    return int(row["new_id"]) if row else None

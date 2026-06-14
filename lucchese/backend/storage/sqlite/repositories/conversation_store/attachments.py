"""
storage/sqlite/repositories/conversation_store/attachments.py
Attachment behavioural rows in the canonical store (Rule 9, Rule 23).

kind ∈ upload | generated_image | image_asset_pointer | file.
"""

from __future__ import annotations

import sqlite3

_INSERT = """
INSERT INTO attachments (
    conversation_id, message_id, source, kind, source_asset_id, name, mime_type,
    url, size, width, height, created_at
) VALUES (
    :conversation_id, :message_id, :source, :kind, :source_asset_id, :name, :mime_type,
    :url, :size, :width, :height, :created_at
)
"""


def insert(con: sqlite3.Connection, row: dict) -> int:
    """Insert one attachment; return the assigned integer id."""
    params = {
        "conversation_id": row["conversation_id"],
        "message_id": row["message_id"],
        "source": row["source"],
        "kind": row.get("kind"),
        "source_asset_id": row.get("source_asset_id"),
        "name": row.get("name"),
        "mime_type": row.get("mime_type"),
        "url": row.get("url"),
        "size": row.get("size"),
        "width": row.get("width"),
        "height": row.get("height"),
        "created_at": row.get("created_at"),
    }
    cur = con.execute(_INSERT, params)
    return int(cur.lastrowid)

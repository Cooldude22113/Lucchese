"""
storage/sqlite/repositories/conversation_store/tool_calls.py
Tool-call behavioural rows in the canonical store (Rule 9, Rule 23).
"""

from __future__ import annotations

import sqlite3

_INSERT = """
INSERT INTO tool_calls (
    conversation_id, message_id, source, tool_name, command, arguments, created_at
) VALUES (
    :conversation_id, :message_id, :source, :tool_name, :command, :arguments, :created_at
)
"""


def insert(con: sqlite3.Connection, row: dict) -> int:
    """Insert one tool_call; return the assigned integer id."""
    params = {
        "conversation_id": row["conversation_id"],
        "message_id": row["message_id"],
        "source": row["source"],
        "tool_name": row.get("tool_name"),
        "command": row.get("command"),
        "arguments": row.get("arguments"),
        "created_at": row.get("created_at"),
    }
    cur = con.execute(_INSERT, params)
    return int(cur.lastrowid)

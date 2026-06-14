"""
storage/sqlite/repositories/conversation_store/reasoning_traces.py
Reasoning-trace behavioural rows in the canonical store (Rule 9, Rule 23).

kind ∈ thinking_trace | agent_thinking_trace | step.
"""

from __future__ import annotations

import sqlite3

_INSERT = """
INSERT INTO reasoning_traces (
    conversation_id, message_id, source, kind, content, started_at, ended_at, seq
) VALUES (
    :conversation_id, :message_id, :source, :kind, :content, :started_at, :ended_at, :seq
)
"""


def insert(con: sqlite3.Connection, row: dict) -> int:
    """Insert one reasoning_trace; return the assigned integer id."""
    params = {
        "conversation_id": row["conversation_id"],
        "message_id": row["message_id"],
        "source": row["source"],
        "kind": row.get("kind"),
        "content": row.get("content"),
        "started_at": row.get("started_at"),
        "ended_at": row.get("ended_at"),
        "seq": row.get("seq"),
    }
    cur = con.execute(_INSERT, params)
    return int(cur.lastrowid)

"""
storage/sqlite/repositories/conversation_store/web_searches.py
Web-search behavioural rows in the canonical store (Rule 9, Rule 23).

search_results may reference a web_search via web_search_id, so insert() returns
the assigned id for the pipeline to thread results onto.
"""

from __future__ import annotations

import sqlite3

_INSERT = """
INSERT INTO web_searches (
    conversation_id, message_id, source, query, num_results, search_source, created_at
) VALUES (
    :conversation_id, :message_id, :source, :query, :num_results, :search_source, :created_at
)
"""


def insert(con: sqlite3.Connection, row: dict) -> int:
    """Insert one web_search; return the assigned integer id."""
    params = {
        "conversation_id": row["conversation_id"],
        "message_id": row["message_id"],
        "source": row["source"],
        "query": row.get("query"),
        "num_results": row.get("num_results"),
        "search_source": row.get("search_source"),
        "created_at": row.get("created_at"),
    }
    cur = con.execute(_INSERT, params)
    return int(cur.lastrowid)

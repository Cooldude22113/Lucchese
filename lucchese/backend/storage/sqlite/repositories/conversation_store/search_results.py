"""
storage/sqlite/repositories/conversation_store/search_results.py
Search-result behavioural rows in the canonical store (Rule 9, Rule 23).

kind ∈ search_result | citation | tether_quote | safe_url | xpost | image.
"""

from __future__ import annotations

import sqlite3

_INSERT = """
INSERT INTO search_results (
    conversation_id, message_id, web_search_id, source, kind, url, domain,
    title, snippet, pub_date, rank, created_at
) VALUES (
    :conversation_id, :message_id, :web_search_id, :source, :kind, :url, :domain,
    :title, :snippet, :pub_date, :rank, :created_at
)
"""


def insert(con: sqlite3.Connection, row: dict) -> int:
    """Insert one search_result; return the assigned integer id."""
    params = {
        "conversation_id": row["conversation_id"],
        "message_id": row["message_id"],
        "web_search_id": row.get("web_search_id"),
        "source": row["source"],
        "kind": row.get("kind"),
        "url": row.get("url"),
        "domain": row.get("domain"),
        "title": row.get("title"),
        "snippet": row.get("snippet"),
        "pub_date": row.get("pub_date"),
        "rank": row.get("rank"),
        "created_at": row.get("created_at"),
    }
    cur = con.execute(_INSERT, params)
    return int(cur.lastrowid)

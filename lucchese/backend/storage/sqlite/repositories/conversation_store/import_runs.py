"""
storage/sqlite/repositories/conversation_store/import_runs.py
Import-run bookkeeping rows in the canonical store (Rule 9, Rule 23).

One row per import invocation: opened at start(), closed at finish() with the
totals and the serialised report. Read helpers back the status endpoint.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from config.paths import CONVERSATION_STORE_DB
from storage.sqlite.connection import session


def start(source: str, files: list[str] | None = None) -> int:
    """Open an import_runs row; return its id."""
    now = datetime.now(timezone.utc).isoformat()
    with session(CONVERSATION_STORE_DB) as con:
        cur = con.execute(
            "INSERT INTO import_runs (source, started_at, files) VALUES (?, ?, ?)",
            (source, now, json.dumps(files or [])),
        )
        return int(cur.lastrowid)


def finish(
    run_id: int,
    conversations_imported: int,
    messages_imported: int,
    errors: int,
    report: dict | None = None,
) -> None:
    """Close an import_runs row with totals and the serialised report."""
    now = datetime.now(timezone.utc).isoformat()
    with session(CONVERSATION_STORE_DB) as con:
        con.execute(
            """
            UPDATE import_runs
               SET finished_at = ?, conversations_imported = ?,
                   messages_imported = ?, errors = ?, report = ?
             WHERE id = ?
            """,
            (
                now,
                conversations_imported,
                messages_imported,
                errors,
                json.dumps(report or {}),
                run_id,
            ),
        )


def recent(limit: int = 10) -> list[dict]:
    """Status helper: most recent import runs, newest first."""
    with session(CONVERSATION_STORE_DB) as con:
        rows = con.execute(
            "SELECT * FROM import_runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        for key in ("files", "report"):
            if d.get(key):
                try:
                    d[key] = json.loads(d[key])
                except (ValueError, TypeError):
                    pass
        out.append(d)
    return out

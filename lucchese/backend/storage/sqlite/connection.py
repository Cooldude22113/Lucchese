"""
storage/sqlite/connection.py
SQLite connection mechanics (Rule 9: storage owns persistence mechanics).

Two distinct databases live here:
  - conversations.db  (CONVERSATIONS_DB) — conversations, messages, documents, roleplay
  - lucchese_state.db (STATE_DB)         — projects, tasks, decisions, blockers, state

Connection paths come from config/paths.py (Rule 1) so nothing hardcodes a relative
path. Two access styles are provided:
  - get_con() / get_state_con(): bare Row-factory connection; caller manages commit/close.
  - session(path) / state_session(): context manager that commits on success, rolls
    back on error, and always closes.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from config.paths import CONVERSATIONS_DB, STATE_DB


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection with a Row factory for dict-like access."""
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def get_con() -> sqlite3.Connection:
    """Bare connection to the conversations database. Caller commits/closes."""
    return connect(CONVERSATIONS_DB)


def get_state_con() -> sqlite3.Connection:
    """Bare connection to the state database. Caller commits/closes."""
    return connect(STATE_DB)


@contextmanager
def session(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    """
    Transactional context manager: commit on clean exit, rollback on exception,
    always close.
    """
    con = connect(db_path)
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


@contextmanager
def state_session() -> Iterator[sqlite3.Connection]:
    """Transactional context manager bound to the state database."""
    with session(STATE_DB) as con:
        yield con

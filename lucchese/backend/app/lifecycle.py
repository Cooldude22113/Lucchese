"""
app/lifecycle.py
Startup sequence (Rule 3, Rule 15).

Order is load-bearing:
  1. ensure runtime data directories exist
  2. initialise both SQLite databases (schema + migrations)
  3. run startup validation (read-only; hard-stops on critical failure)
"""

from __future__ import annotations

from config.paths import ensure_runtime_dirs
from observability.startup_validator import run_startup_validation
from storage.sqlite.schema import init_conversations_db, init_state_db


def run_startup() -> None:
    """Prepare data dirs, initialise the databases, then validate."""
    ensure_runtime_dirs()
    init_conversations_db()
    init_state_db()
    run_startup_validation()  # must run after the DBs are initialised

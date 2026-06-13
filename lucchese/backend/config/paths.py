"""
config/paths.py
Single source of truth for every filesystem location the backend uses.

Rule 1 (separate runtime data from source) + Rule 24 (ignore runtime files in Git):
all runtime artefacts live under backend/data/. Source code must import these
constants instead of hardcoding relative paths, so the working directory of the
process no longer changes where data is read from or written to.

Resolution is anchored to this file's location (backend/config/paths.py), making
paths independent of the current working directory.
"""

from __future__ import annotations

from pathlib import Path

# backend/config/paths.py -> parents[0]=config, parents[1]=backend
BACKEND_DIR: Path = Path(__file__).resolve().parents[1]

# ── Runtime data root (Rule 1) ────────────────────────────────────────────────
DATA_DIR:           Path = BACKEND_DIR / "data"
SQLITE_DIR:         Path = DATA_DIR / "sqlite"
CHROMA_DIR:         Path = DATA_DIR / "chroma"
GENERATED_DOCS_DIR: Path = DATA_DIR / "generated_docs"
LOGS_DIR:           Path = DATA_DIR / "logs"
UPLOADS_DIR:        Path = DATA_DIR / "uploads"
AUDIO_DIR:          Path = DATA_DIR / "audio"
CACHE_DIR:          Path = DATA_DIR / "cache"
TEMP_DIR:           Path = DATA_DIR / "temp"

# ── Database files ────────────────────────────────────────────────────────────
# Two distinct databases, kept distinct:
#   conversations.db  — conversations, messages, documents, roleplay, errors
#   lucchese_state.db — projects, tasks, decisions, blockers, daily/profile state
CONVERSATIONS_DB: Path = SQLITE_DIR / "conversations.db"
STATE_DB:         Path = SQLITE_DIR / "lucchese_state.db"

# ── Vector store ──────────────────────────────────────────────────────────────
# ChromaDB PersistentClient wants a string path.
CHROMA_PATH: str = str(CHROMA_DIR)

# ── Log files ─────────────────────────────────────────────────────────────────
CONTEXT_LOG_PATH: Path = LOGS_DIR / "lucchese.context.log"
STARTUP_LOG_PATH: Path = LOGS_DIR / "lucchese.startup.log"


def ensure_runtime_dirs() -> None:
    """
    Create every runtime data directory if absent. Idempotent.

    Call once at startup (app/lifecycle.py) before init_db / chroma client / doc
    generation so first run on a clean checkout does not fail on a missing dir.
    """
    for directory in (
        SQLITE_DIR,
        CHROMA_DIR,
        GENERATED_DOCS_DIR,
        LOGS_DIR,
        UPLOADS_DIR,
        AUDIO_DIR,
        CACHE_DIR,
        TEMP_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)

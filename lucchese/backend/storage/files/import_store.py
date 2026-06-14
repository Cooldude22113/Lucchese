"""
storage/files/import_store.py
Filesystem access for raw import exports (Rule 9: storage owns file mechanics).

Discovers the raw ChatGPT/Grok export files under IMPORTS_RAW_DIR and, optionally,
archives a file into IMPORTS_PROCESSED_DIR after a successful import. Paths come
from config/paths.py (Rule 1); filenames/globs come from config/ingestion_settings.py.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from config.ingestion_settings import CHATGPT_GLOB, GROK_FILENAME
from config.paths import IMPORTS_PROCESSED_DIR, IMPORTS_RAW_DIR


def list_chatgpt_files() -> list[Path]:
    """Return the ChatGPT export files in the raw dir, sorted by name."""
    return sorted(IMPORTS_RAW_DIR.glob(CHATGPT_GLOB))


def grok_file() -> Path | None:
    """Return the Grok export file in the raw dir, or None if absent."""
    path = IMPORTS_RAW_DIR / GROK_FILENAME
    return path if path.exists() else None


def list_raw_files(source: str) -> list[Path]:
    """Return the raw files for a given source ('chatgpt' | 'grok')."""
    if source == "chatgpt":
        return list_chatgpt_files()
    if source == "grok":
        g = grok_file()
        return [g] if g else []
    raise ValueError(f"Unknown import source: {source!r}")


def archive(path: Path) -> Path:
    """Move a processed raw file into IMPORTS_PROCESSED_DIR; return the new path."""
    IMPORTS_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    dest = IMPORTS_PROCESSED_DIR / path.name
    shutil.move(str(path), str(dest))
    return dest

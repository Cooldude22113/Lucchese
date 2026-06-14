"""
config/ingestion_settings.py
Tunable VALUES for the import/ingestion subsystem (Rule 16).

The sources, parsers, and pipelines in ingestion/ read these constants instead of
hardcoding filenames or batch sizes. Config stores values; ingestion enforces
behaviour.
"""

from __future__ import annotations

# ── Raw export discovery ──────────────────────────────────────────────────────
# ChatGPT exports arrive as a numbered set: conversations-000.json … conversations-NNN.json.
CHATGPT_GLOB: str = "conversations-*.json"
# Grok export is a single backend dump.
GROK_FILENAME: str = "prod-grok-backend.json"

# ── Import behaviour ──────────────────────────────────────────────────────────
# Number of conversations to persist between commits inside a source run.
IMPORT_BATCH_SIZE: int = 100
# When True, raw files are moved to IMPORTS_PROCESSED_DIR after a successful run.
# Kept False by default: re-running is idempotent (UNIQUE + id_map), so leaving the
# raw files in place is safe and keeps the source of truth visible.
ARCHIVE_AFTER_IMPORT: bool = False

# ── Sources this pipeline understands ─────────────────────────────────────────
SUPPORTED_SOURCES: tuple[str, ...] = ("chatgpt", "grok")

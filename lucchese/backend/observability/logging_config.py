"""
observability/logging_config.py
Logger configuration for the structured JSON log streams (Rule 15).

Two named loggers carry pre-serialised JSON messages:
  - "lucchese.startup" — startup validation entries
  - "lucchese.context" — per-inference context-assembly entries (with file rotation)

A passthrough formatter emits each record's message as-is so the JSON structure is
preserved. configure_logging() wires both and is called once at startup.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from config.paths import CONTEXT_LOG_PATH, LOGS_DIR

# Context log rotation: 5 MB × 5 backups ≈ 25 MB cap.
_CONTEXT_LOG_MAX_BYTES = 5_242_880
_CONTEXT_LOG_BACKUP_COUNT = 5


class PassthroughJsonFormatter(logging.Formatter):
    """Emit records whose msg is already a JSON string without re-wrapping."""

    def format(self, record: logging.LogRecord) -> str:
        return record.getMessage()


def _iso_ts() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def configure_startup_logger() -> None:
    """Console handler for the lucchese.startup logger (idempotent)."""
    logger = logging.getLogger("lucchese.startup")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(PassthroughJsonFormatter())
        logger.addHandler(handler)
    logger.propagate = False


def configure_context_logger() -> None:
    """Console + rotating-file handlers for the lucchese.context logger (idempotent)."""
    logger = logging.getLogger("lucchese.context")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return

    formatter = PassthroughJsonFormatter()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        filename=str(CONTEXT_LOG_PATH),
        maxBytes=_CONTEXT_LOG_MAX_BYTES,
        backupCount=_CONTEXT_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    logger.propagate = False


def configure_logging() -> None:
    """Configure all structured loggers and emit startup confirmation entries."""
    configure_startup_logger()
    configure_context_logger()

    ts = _iso_ts()
    logging.getLogger("lucchese.context").info(json.dumps({
        "event": "context_logging_initialized",
        "timestamp": ts,
        "logger_name": "lucchese.context",
        "log_level": "INFO",
    }))
    logging.getLogger("lucchese.context").info(json.dumps({
        "event": "log_rotation_initialized",
        "handler": "RotatingFileHandler",
        "max_bytes": _CONTEXT_LOG_MAX_BYTES,
        "backup_count": _CONTEXT_LOG_BACKUP_COUNT,
        "log_path": str(CONTEXT_LOG_PATH),
    }))

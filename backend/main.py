import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.database import init_db
from routes.chat import router as chat_router
from routes.admin import router as admin_router
from routes.conversations import router as conv_router
from routes.files import router as files_router
from routes.voice import router as voice_router
from routes.shopify import router as shopify_router
from routes.deal import router as deal_router
from routes.state import router as state_router, init_state_db
from routes.startup_validator import run_startup_validation


# ── Context assembly logger (STAB-001 / STAB-003) ────────────────────────────
# Scoped to "lucchese.context" only — does NOT touch the root logger format.
# Messages are pre-serialised JSON strings; the formatter passes them through
# as-is to preserve machine-readable structure in the log stream.
#
# STAB-003: A RotatingFileHandler is registered alongside the StreamHandler.
# Rotation parameters: maxBytes=5_242_880 (5 MB), backupCount=5.
# Total disk cap for this stream: ~25 MB across 5 backup files.
# At ~400 bytes/entry and 100 inferences/day, a single file holds ~3–6 months
# of heavy use before rotation fires.

_CONTEXT_LOG_PATH = "lucchese.context.log"
_CONTEXT_LOG_MAX_BYTES = 5_242_880   # 5 MB
_CONTEXT_LOG_BACKUP_COUNT = 5


class _PassthroughJsonFormatter(logging.Formatter):
    """Emit log records whose msg is already a JSON string without re-wrapping."""
    def format(self, record: logging.LogRecord) -> str:
        return record.getMessage()


def _configure_context_logger() -> None:
    formatter = _PassthroughJsonFormatter()

    # Console handler — unchanged from STAB-001.
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    # File handler — added by STAB-003. Uses the same formatter instance
    # to guarantee format parity between console and file output.
    file_handler = RotatingFileHandler(
        filename=_CONTEXT_LOG_PATH,
        maxBytes=_CONTEXT_LOG_MAX_BYTES,
        backupCount=_CONTEXT_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    context_logger = logging.getLogger("lucchese.context")
    context_logger.setLevel(logging.INFO)
    context_logger.addHandler(stream_handler)
    context_logger.addHandler(file_handler)
    context_logger.propagate = False   # prevent double-emission via root logger


_configure_context_logger()

# Startup confirmation — confirms logging infrastructure is active (STAB-001).
_startup_ts = datetime.now(timezone.utc)
logging.getLogger("lucchese.context").info(json.dumps({
    "event":       "context_logging_initialized",
    "timestamp":   _startup_ts.strftime("%Y-%m-%dT%H:%M:%S.") +
                   f"{_startup_ts.microsecond // 1000:03d}Z",
    "logger_name": "lucchese.context",
    "log_level":   "INFO",
}))

# Rotation configuration confirmation — STAB-003.
# Records the active rotation parameters in the log stream so that any future
# parameter change is visible in the history at the exact startup it took effect.
logging.getLogger("lucchese.context").info(json.dumps({
    "event":        "log_rotation_initialized",
    "handler":      "RotatingFileHandler",
    "max_bytes":    _CONTEXT_LOG_MAX_BYTES,
    "backup_count": _CONTEXT_LOG_BACKUP_COUNT,
    "log_path":     os.path.abspath(_CONTEXT_LOG_PATH),
}))

# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://192.168.1.112:5173",
        "https://lucchese.app",
        "https://www.lucchese.app",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
init_state_db()
run_startup_validation()   # STAB-005 — must run after init_db() and init_state_db()

app.include_router(chat_router)
app.include_router(admin_router)
app.include_router(conv_router)
app.include_router(files_router)
app.include_router(voice_router)
app.include_router(shopify_router)
app.include_router(deal_router)
app.include_router(state_router)

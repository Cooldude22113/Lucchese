"""
startup_validator.py
STAB-005 — Startup Validation and State Layer Lifecycle Integrity

Runs once at startup, after init_db() and init_state_db(), before the
server accepts any traffic. Emits structured log entries to the
"lucchese.startup" logger. Hard-stops the process on critical failures.
Returns normally (with a StartupValidationResult) on degraded or OK outcomes.

This module is read-only with respect to the database and ChromaDB.
It does NOT create, modify, seed, or repair any data or schema.

────────────────────────────────────────────────────────────────────────────
MAINTENANCE OBLIGATION — CANONICAL_STATE_SCHEMA
────────────────────────────────────────────────────────────────────────────
CANONICAL_STATE_SCHEMA is hardcoded here and must be kept in sync with
init_state_db() in routes/state.py whenever that function is modified.

It is intentionally NOT generated dynamically from state.py at runtime.
A separate schema file would introduce its own class of drift. The hardcoded
dict breaks readably when state.py evolves — the validator hard-stops on
schema drift and the maintenance gap becomes immediately visible.

When you modify routes/state.py schema, update CANONICAL_STATE_SCHEMA here.
────────────────────────────────────────────────────────────────────────────
"""

import json
import logging
import os
import sqlite3
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── Startup logger ────────────────────────────────────────────────────────────
# Logger name "lucchese.startup" is distinct from "lucchese.context"
# (inference-time) so startup entries are identifiable by logger name alone.
# Both may write to the same stream or file — that is a deployment decision.

class _PassthroughJsonFormatter(logging.Formatter):
    """Emit pre-serialised JSON strings without re-wrapping."""
    def format(self, record: logging.LogRecord) -> str:
        return record.getMessage()


def _configure_startup_logger() -> None:
    formatter = _PassthroughJsonFormatter()
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger = logging.getLogger("lucchese.startup")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        logger.addHandler(handler)
    logger.propagate = False  # prevent double-emission via root logger


_configure_startup_logger()
_log = logging.getLogger("lucchese.startup")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ts() -> str:
    """ISO 8601 timestamp for log entries."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    check_name: str
    status: str          # "ok" | "failed" | "degraded" | "warning" | "skipped"
    detail: str
    failure_policy: str  # "hard_stop" | "degraded_start" | "warning"


@dataclass
class StartupValidationResult:
    overall_status: str          # "ok" | "degraded" | "failed"
    checks: list
    should_abort: bool
    degraded_components: list
    failed_components: list
    warning_components: list

    @classmethod
    def build(cls, checks: list) -> "StartupValidationResult":
        should_abort = any(
            c.status == "failed" and c.failure_policy == "hard_stop"
            for c in checks
        )
        degraded: list[str] = []
        failed: list[str] = []
        warnings: list[str] = []
        overall = "ok"

        for c in checks:
            if c.status == "failed":
                failed.append(c.check_name)
                overall = "failed"
            elif c.status == "degraded":
                degraded.append(c.check_name)
                if overall == "ok":
                    overall = "degraded"
            elif c.status == "warning":
                warnings.append(c.check_name)
            # "skipped" and "ok" do not alter overall_status

        return cls(
            overall_status=overall,
            checks=checks,
            should_abort=should_abort,
            degraded_components=degraded,
            failed_components=failed,
            warning_components=warnings,
        )


# ── Canonical schema ──────────────────────────────────────────────────────────
# Sourced directly from routes/state.py init_state_db() and apply_migrations().
# apply_migrations() adds confirmed and field_meta to existing installs; both
# are now present in the CREATE TABLE block as of the current schema version.
#
# Column presence is checked; column type is not checked (out of scope).
# Extra columns in the live table beyond this list are a warning, not an error.

CANONICAL_STATE_SCHEMA: dict[str, list[str]] = {
    "profile_state": [
        "id",
        "age",
        "active_course",
        "course_status",
        "primary_project",
        "active_projects",
        "current_business",
        "training_focus",
        "current_priorities",
        "system_goal",
        "memory_status",
        "historical_context",
        "personality_mode",
        "focus_area",
        "confirmed",
        "field_meta",
        "updated_at",
    ],
    "projects": [
        "id",
        "name",
        "status",
        "current_focus",
        "next_action",
        "created_at",
        "updated_at",
    ],
    "tasks": [
        "id",
        "project_id",
        "title",
        "status",
        "priority",
        "notes",
        "created_at",
        "updated_at",
    ],
    "decisions": [
        "id",
        "project_id",
        "decision",
        "reason",
        "created_at",
    ],
    "blockers": [
        "id",
        "project_id",
        "blocker",
        "status",
        "created_at",
        "resolved_at",
    ],
    "daily_state": [
        "id",
        "active_project",
        "active_mode",
        "current_focus",
        "last_summary",
        "updated_at",
    ],
}

# Conversation DB tables — sourced from routes/database.py init_db().
CANONICAL_CONVERSATION_SCHEMA: dict[str, list[str]] = {
    "conversations": ["id", "created_at", "updated_at", "title"],
    "messages": ["id", "conversation_id", "role", "content", "created_at"],
    "documents": ["id", "filename", "file_type", "chunk_count", "created_at"],
    "roleplay_sessions": ["conversation_id", "exchanges", "created_at"],
}

# ── Environment variable catalogue ────────────────────────────────────────────
# Sourced from routes/chat.py, routes/memory.py, and routes/config.py (inferred).
#
# REQUIRED_ENV_VARS: absence = hard stop.
# PROVIDER_REQUIRED_VARS: required only when CHAT_PROVIDER matches the key.
# OPTIONAL_ENV_VARS: absence = warning only.
#
# Note: OLLAMA_BASE_URL has a hardcoded default of "http://localhost:11434"
# in routes/memory.py. The validator treats its absence as a warning (not hard
# stop) and documents the active default so the operator is aware.
# CHROMA_PATH similarly defaults to "./chroma_db".

REQUIRED_ENV_VARS: list[str] = [
    "CHAT_PROVIDER",
]

VALID_CHAT_PROVIDERS: set[str] = {"ollama", "claude", "openai"}

PROVIDER_REQUIRED_VARS: dict[str, list[str]] = {
    "claude":  ["ANTHROPIC_API_KEY"],
    "openai":  ["OPENAI_API_KEY"],
    # ollama: OLLAMA_BASE_URL has a hardcoded default — warning only if absent
}

OPTIONAL_ENV_VARS: list[str] = [
    "OLLAMA_BASE_URL",    # defaults to http://localhost:11434 in memory.py
    "CHROMA_PATH",        # defaults to ./chroma_db in memory.py
    "MODEL_FAST",         # defaults to gemma2:27b in memory.py
    "MODEL_DEEP",         # set in routes/config.py
    "ELEVENLABS_API_KEY", # TTS — voice routes are experimental
    "SHOPIFY_STORE",      # Shopify integration
    "SHOPIFY_TOKEN",      # Shopify integration
    "GOOGLE_SHEETS_ID",   # Google Sheets integration
]

# Database file paths — sourced from routes/database.py and routes/state.py.
_CONVERSATIONS_DB_PATH = Path("conversations.db")
_STATE_DB_PATH = Path("lucchese_state.db")

# ChromaDB path — read from env with same default as memory.py.
_CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")

# ChromaDB connectivity timeout in seconds.
_CHROMADB_TIMEOUT_SECONDS = 5


# ── Log helpers ───────────────────────────────────────────────────────────────

def _emit_check(result: CheckResult) -> None:
    """Emit one structured log entry for a single check."""
    level = logging.WARNING if result.status in ("warning", "degraded", "failed", "skipped") else logging.INFO
    _log.log(level, json.dumps({
        "logger":         "lucchese.startup",
        "event":          "startup_check",
        "check":          result.check_name,
        "status":         result.status,
        "failure_policy": result.failure_policy,
        "detail":         result.detail,
        "timestamp":      _ts(),
    }))


def _emit_aggregate(result: StartupValidationResult, checks_run: int, checks_skipped: int) -> None:
    """Emit one aggregate log entry after all checks complete."""
    level = logging.WARNING if result.overall_status != "ok" else logging.INFO
    _log.log(level, json.dumps({
        "logger":              "lucchese.startup",
        "event":               "startup_validation_complete",
        "overall_status":      result.overall_status,
        "should_abort":        result.should_abort,
        "degraded_components": result.degraded_components,
        "failed_components":   result.failed_components,
        "warning_components":  result.warning_components,
        "checks_run":          checks_run,
        "checks_skipped":      checks_skipped,
        "timestamp":           _ts(),
    }))


def _emit_abort(check_name: str, detail: str) -> None:
    """Emit abort log entry immediately before sys.exit(1)."""
    _log.error(json.dumps({
        "logger":    "lucchese.startup",
        "event":     "startup_aborted",
        "reason":    check_name,
        "detail":    detail,
        "timestamp": _ts(),
    }))


def _stderr_hard_stop(check_name: str, detail: str) -> None:
    """Print plain-text hard-stop message to stderr."""
    print(
        f"\nLUCCHESE STARTUP FAILED\n"
        f"Check: {check_name}\n"
        f"Reason: {detail}\n"
        f"The server will not start. Resolve the above before restarting.\n",
        file=sys.stderr,
        flush=True,
    )


def _skip(check_name: str, reason: str) -> CheckResult:
    """Produce a skipped CheckResult and emit its log entry."""
    result = CheckResult(
        check_name=check_name,
        status="skipped",
        detail=f"Skipped — {reason}",
        failure_policy="warning",
    )
    _emit_check(result)
    return result


# ── Check functions ───────────────────────────────────────────────────────────

def check_environment() -> list[CheckResult]:
    """
    Check 1 — Environment variable validation.

    Required variables: hard stop on absence or invalid value.
    Provider-specific variables: hard stop if provider is set and key is absent.
    Optional variables: warning only.

    SECURITY: credential values are never logged. Only presence/absence is logged.
    """
    results: list[CheckResult] = []

    # 1a — Required variables
    for var in REQUIRED_ENV_VARS:
        value = os.getenv(var)
        if value is None or value.strip() == "":
            r = CheckResult(
                check_name=f"env.{var}",
                status="failed",
                detail=f"Required environment variable '{var}' is absent or empty.",
                failure_policy="hard_stop",
            )
        else:
            r = CheckResult(
                check_name=f"env.{var}",
                status="ok",
                detail=f"'{var}' is present.",
                failure_policy="hard_stop",
            )
        _emit_check(r)
        results.append(r)

    # 1b — CHAT_PROVIDER value validation (only if present)
    provider_value = os.getenv("CHAT_PROVIDER", "").strip().lower()
    if provider_value and provider_value not in VALID_CHAT_PROVIDERS:
        r = CheckResult(
            check_name="env.CHAT_PROVIDER.value",
            status="failed",
            detail=(
                f"CHAT_PROVIDER value '{provider_value}' is not in the allowed set: "
                f"{sorted(VALID_CHAT_PROVIDERS)}."
            ),
            failure_policy="hard_stop",
        )
        _emit_check(r)
        results.append(r)
    elif provider_value in VALID_CHAT_PROVIDERS:
        r = CheckResult(
            check_name="env.CHAT_PROVIDER.value",
            status="ok",
            detail=f"CHAT_PROVIDER='{provider_value}' is a valid provider.",
            failure_policy="hard_stop",
        )
        _emit_check(r)
        results.append(r)

    # 1c — Provider-specific required variables
    if provider_value in PROVIDER_REQUIRED_VARS:
        for var in PROVIDER_REQUIRED_VARS[provider_value]:
            value = os.getenv(var)
            if value is None or value.strip() == "":
                r = CheckResult(
                    check_name=f"env.{var}",
                    status="failed",
                    detail=(
                        f"CHAT_PROVIDER='{provider_value}' requires '{var}', "
                        f"which is absent or empty."
                    ),
                    failure_policy="hard_stop",
                )
            else:
                # Do NOT log the value — log presence only.
                r = CheckResult(
                    check_name=f"env.{var}",
                    status="ok",
                    detail=f"'{var}' is present (value not logged).",
                    failure_policy="hard_stop",
                )
            _emit_check(r)
            results.append(r)

    # 1d — Optional variables (warning only)
    for var in OPTIONAL_ENV_VARS:
        value = os.getenv(var)
        if value is None or value.strip() == "":
            # Special-case: document hardcoded defaults so operators aren't confused.
            defaults = {
                "OLLAMA_BASE_URL": "http://localhost:11434",
                "CHROMA_PATH":     "./chroma_db",
                "MODEL_FAST":      "gemma2:27b",
            }
            default_note = (
                f" (hardcoded default: '{defaults[var]}')" if var in defaults else ""
            )
            r = CheckResult(
                check_name=f"env.{var}",
                status="warning",
                detail=f"Optional variable '{var}' is absent{default_note}.",
                failure_policy="warning",
            )
        else:
            r = CheckResult(
                check_name=f"env.{var}",
                status="ok",
                detail=f"Optional variable '{var}' is present.",
                failure_policy="warning",
            )
        _emit_check(r)
        results.append(r)

    return results


def check_sqlite_connectivity(db_path: Path, check_name: str) -> CheckResult:
    """
    Check 2 — SQLite connectivity.

    Opens a read-only connection to confirm the file is accessible.
    Does not modify state.
    """
    try:
        # Use URI with mode=ro to confirm file is readable without any writes.
        uri = f"file:{db_path.resolve()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.close()
        r = CheckResult(
            check_name=check_name,
            status="ok",
            detail=f"Database '{db_path}' opened successfully (read-only).",
            failure_policy="hard_stop",
        )
    except Exception as exc:
        r = CheckResult(
            check_name=check_name,
            status="failed",
            detail=f"Cannot open database '{db_path}': {exc}",
            failure_policy="hard_stop",
        )
    _emit_check(r)
    return r


def check_required_tables(
    db_path: Path,
    expected_tables: dict[str, list[str]],
    check_name_prefix: str,
) -> list[CheckResult]:
    """
    Check 3 — Required tables present.

    Uses PRAGMA table_list to confirm each expected table exists.
    Returns one CheckResult per table.
    """
    results: list[CheckResult] = []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("PRAGMA table_list").fetchall()
        live_tables = {row["name"] for row in rows}
        conn.close()
    except Exception as exc:
        # If we can't even PRAGMA, emit one failed result covering all tables.
        r = CheckResult(
            check_name=f"{check_name_prefix}.table_list",
            status="failed",
            detail=f"PRAGMA table_list failed on '{db_path}': {exc}",
            failure_policy="hard_stop",
        )
        _emit_check(r)
        results.append(r)
        return results

    for table_name in expected_tables:
        if table_name in live_tables:
            r = CheckResult(
                check_name=f"{check_name_prefix}.table.{table_name}",
                status="ok",
                detail=f"Table '{table_name}' exists in '{db_path}'.",
                failure_policy="hard_stop",
            )
        else:
            r = CheckResult(
                check_name=f"{check_name_prefix}.table.{table_name}",
                status="failed",
                detail=f"Required table '{table_name}' is missing from '{db_path}'.",
                failure_policy="hard_stop",
            )
        _emit_check(r)
        results.append(r)

    return results


def check_state_schema(
    db_path: Path,
    canonical_schema: dict[str, list[str]],
    tables_present: set[str],
    check_name_prefix: str,
) -> list[CheckResult]:
    """
    Check 4 — State layer schema integrity.

    For each table that is confirmed present, runs PRAGMA table_info and
    compares column names against the canonical expected list.

    Missing expected column = hard stop (schema drift).
    Extra column beyond canonical list = warning only.

    Skips tables that are not in tables_present (already failed in check 3).
    """
    results: list[CheckResult] = []

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    except Exception as exc:
        r = CheckResult(
            check_name=f"{check_name_prefix}.schema_open",
            status="failed",
            detail=f"Cannot open '{db_path}' for schema check: {exc}",
            failure_policy="hard_stop",
        )
        _emit_check(r)
        results.append(r)
        return results

    for table_name, expected_columns in canonical_schema.items():
        check_name = f"{check_name_prefix}.schema.{table_name}"

        if table_name not in tables_present:
            results.append(_skip(check_name, f"table '{table_name}' was not confirmed present"))
            continue

        try:
            rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            live_columns = {row["name"] for row in rows}
        except Exception as exc:
            r = CheckResult(
                check_name=check_name,
                status="failed",
                detail=f"PRAGMA table_info({table_name}) failed: {exc}",
                failure_policy="hard_stop",
            )
            _emit_check(r)
            results.append(r)
            continue

        expected_set = set(expected_columns)
        missing = expected_set - live_columns
        extra = live_columns - expected_set

        if missing:
            r = CheckResult(
                check_name=check_name,
                status="failed",
                detail=(
                    f"Schema drift in '{table_name}': expected columns absent: "
                    f"{sorted(missing)}."
                ),
                failure_policy="hard_stop",
            )
        elif extra:
            r = CheckResult(
                check_name=check_name,
                status="warning",
                detail=(
                    f"'{table_name}' has extra columns beyond canonical schema "
                    f"(not drift — may be intentional additions): {sorted(extra)}."
                ),
                failure_policy="warning",
            )
        else:
            r = CheckResult(
                check_name=check_name,
                status="ok",
                detail=f"'{table_name}' schema matches canonical definition.",
                failure_policy="hard_stop",
            )

        _emit_check(r)
        results.append(r)

    conn.close()
    return results


def check_profile_state_row(db_path: Path, schema_ok: bool) -> CheckResult:
    """
    Check 5 — profile_state row integrity.

    Confirms whether the single required row (id=1) exists.
    Row absent = warning (expected initial state).
    Query failure = hard stop.

    This check is skipped if the schema check for profile_state failed,
    because the query would be meaningless against a broken table.

    The warning emitted here ("not_seeded") is semantically consistent
    with the inference-time "empty_source" signal from STAB-001:
    both are readings of the same absent-Tier-1 condition at different
    points in the request lifecycle.
    """
    check_name = "state.profile_state.row_presence"

    if not schema_ok:
        return _skip(check_name, "profile_state schema check did not pass")

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT id FROM profile_state WHERE id = 1").fetchone()
        conn.close()
    except Exception as exc:
        r = CheckResult(
            check_name=check_name,
            status="failed",
            detail=f"profile_state row query failed unexpectedly: {exc}",
            failure_policy="hard_stop",
        )
        _emit_check(r)
        return r

    if row is None:
        r = CheckResult(
            check_name=check_name,
            status="warning",
            detail=(
                "profile_state row is absent (tier1_status: not_seeded). "
                "Tier 1 context will be empty at inference time. "
                "Populate via PATCH /state/profile or seed_profile.py."
            ),
            failure_policy="warning",
        )
    else:
        r = CheckResult(
            check_name=check_name,
            status="ok",
            detail="profile_state row (id=1) is present.",
            failure_policy="hard_stop",
        )

    _emit_check(r)
    return r


def check_chromadb_connectivity(chroma_path: str) -> CheckResult:
    """
    Check 6 — ChromaDB connectivity.

    Current configuration uses PersistentClient (local filesystem path),
    not HTTP. A threading timeout bounds the check against filesystem edge
    cases (locked files, corrupt state, slow storage).

    ChromaDB unreachable = degraded start (not hard stop). The server
    continues but memory retrieval will fail at inference time. STAB-001
    tier population signals will capture that at runtime.

    IMPORTANT: This check uses the same CHROMA_PATH value as memory.py
    to ensure the connectivity probe targets the same database the live
    system will use.
    """
    check_name = "chromadb.connectivity"
    result_container: list[Optional[CheckResult]] = [None]

    def _probe():
        try:
            import chromadb as _chromadb
            client = _chromadb.PersistentClient(path=chroma_path)
            client.list_collections()
            result_container[0] = CheckResult(
                check_name=check_name,
                status="ok",
                detail=f"ChromaDB reachable at path '{chroma_path}'.",
                failure_policy="degraded_start",
            )
        except Exception as exc:
            result_container[0] = CheckResult(
                check_name=check_name,
                status="degraded",
                detail=f"ChromaDB unavailable at '{chroma_path}': {exc}",
                failure_policy="degraded_start",
            )

    thread = threading.Thread(target=_probe, daemon=True)
    thread.start()
    thread.join(timeout=_CHROMADB_TIMEOUT_SECONDS)

    if thread.is_alive():
        # Thread did not complete within the timeout window.
        r = CheckResult(
            check_name=check_name,
            status="degraded",
            detail=(
                f"ChromaDB connectivity check timed out after "
                f"{_CHROMADB_TIMEOUT_SECONDS}s at path '{chroma_path}'. "
                "Memory retrieval will fail at inference time."
            ),
            failure_policy="degraded_start",
        )
    elif result_container[0] is None:
        r = CheckResult(
            check_name=check_name,
            status="degraded",
            detail="ChromaDB probe returned no result (unexpected).",
            failure_policy="degraded_start",
        )
    else:
        r = result_container[0]

    _emit_check(r)
    return r


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run_startup_validation() -> StartupValidationResult:
    """
    Run all startup checks in sequence and enforce failure policy.

    Called once from main.py after init_db() and init_state_db().
    Returns StartupValidationResult on OK or degraded outcomes.
    Calls sys.exit(1) on hard-stop conditions.

    Check ordering is load-bearing:
      1. Environment  — must pass before anything else is meaningful
      2. SQLite connectivity (state DB, then conversations DB)
      3. Required tables present
      4. Schema integrity per table
      5. profile_state row presence
      6. ChromaDB connectivity

    Later checks depend on earlier ones. Skipping on failure is explicit.
    """
    all_checks: list[CheckResult] = []
    checks_skipped = 0

    _log.info(json.dumps({
        "logger":    "lucchese.startup",
        "event":     "startup_validation_begin",
        "timestamp": _ts(),
    }))

    # ── 1. Environment variables ──────────────────────────────────────────────
    env_results = check_environment()
    all_checks.extend(env_results)
    env_hard_stop = any(r.status == "failed" and r.failure_policy == "hard_stop" for r in env_results)

    # ── 2. SQLite connectivity ────────────────────────────────────────────────
    state_db_ok = False
    conv_db_ok = False

    state_conn_result = check_sqlite_connectivity(_STATE_DB_PATH, "sqlite.state_db.connectivity")
    all_checks.append(state_conn_result)
    if state_conn_result.status == "ok":
        state_db_ok = True

    conv_conn_result = check_sqlite_connectivity(_CONVERSATIONS_DB_PATH, "sqlite.conversations_db.connectivity")
    all_checks.append(conv_conn_result)
    if conv_conn_result.status == "ok":
        conv_db_ok = True

    # ── 3. Required tables present ────────────────────────────────────────────
    state_tables_present: set[str] = set()
    conv_tables_present: set[str] = set()

    if state_db_ok:
        state_table_results = check_required_tables(
            _STATE_DB_PATH,
            CANONICAL_STATE_SCHEMA,
            "sqlite.state_db",
        )
        all_checks.extend(state_table_results)
        for r in state_table_results:
            # Extract table name from check_name: "sqlite.state_db.table.<name>"
            if r.status == "ok":
                parts = r.check_name.split(".")
                if len(parts) >= 4:
                    state_tables_present.add(parts[3])
    else:
        count = len(CANONICAL_STATE_SCHEMA)
        checks_skipped += count
        for table_name in CANONICAL_STATE_SCHEMA:
            all_checks.append(_skip(
                f"sqlite.state_db.table.{table_name}",
                "state DB connectivity failed",
            ))

    if conv_db_ok:
        conv_table_results = check_required_tables(
            _CONVERSATIONS_DB_PATH,
            CANONICAL_CONVERSATION_SCHEMA,
            "sqlite.conversations_db",
        )
        all_checks.extend(conv_table_results)
        for r in conv_table_results:
            if r.status == "ok":
                parts = r.check_name.split(".")
                if len(parts) >= 4:
                    conv_tables_present.add(parts[3])
    else:
        count = len(CANONICAL_CONVERSATION_SCHEMA)
        checks_skipped += count
        for table_name in CANONICAL_CONVERSATION_SCHEMA:
            all_checks.append(_skip(
                f"sqlite.conversations_db.table.{table_name}",
                "conversations DB connectivity failed",
            ))

    # ── 4. Schema integrity ───────────────────────────────────────────────────
    if state_db_ok:
        state_schema_results = check_state_schema(
            _STATE_DB_PATH,
            CANONICAL_STATE_SCHEMA,
            state_tables_present,
            "sqlite.state_db",
        )
        all_checks.extend(state_schema_results)
    else:
        checks_skipped += len(CANONICAL_STATE_SCHEMA)
        for table_name in CANONICAL_STATE_SCHEMA:
            all_checks.append(_skip(
                f"sqlite.state_db.schema.{table_name}",
                "state DB connectivity failed",
            ))

    if conv_db_ok:
        conv_schema_results = check_state_schema(
            _CONVERSATIONS_DB_PATH,
            CANONICAL_CONVERSATION_SCHEMA,
            conv_tables_present,
            "sqlite.conversations_db",
        )
        all_checks.extend(conv_schema_results)
    else:
        checks_skipped += len(CANONICAL_CONVERSATION_SCHEMA)
        for table_name in CANONICAL_CONVERSATION_SCHEMA:
            all_checks.append(_skip(
                f"sqlite.conversations_db.schema.{table_name}",
                "conversations DB connectivity failed",
            ))

    # ── 5. profile_state row presence ─────────────────────────────────────────
    profile_schema_ok = any(
        r.check_name == "sqlite.state_db.schema.profile_state" and r.status == "ok"
        for r in all_checks
    )
    if state_db_ok:
        profile_row_result = check_profile_state_row(_STATE_DB_PATH, profile_schema_ok)
        all_checks.append(profile_row_result)
    else:
        checks_skipped += 1
        all_checks.append(_skip(
            "state.profile_state.row_presence",
            "state DB connectivity failed",
        ))

    # ── 6. ChromaDB connectivity ──────────────────────────────────────────────
    chroma_result = check_chromadb_connectivity(_CHROMA_PATH)
    all_checks.append(chroma_result)

    # ── Aggregate result and emit ─────────────────────────────────────────────
    checks_run = len(all_checks) - checks_skipped
    result = StartupValidationResult.build(all_checks)
    _emit_aggregate(result, checks_run, checks_skipped)

    # ── Hard stop enforcement ─────────────────────────────────────────────────
    if result.should_abort:
        # Identify the specific triggering check for the abort log and stderr.
        triggering = next(
            (c for c in all_checks if c.status == "failed" and c.failure_policy == "hard_stop"),
            None,
        )
        trigger_name = triggering.check_name if triggering else "unknown"
        trigger_detail = triggering.detail if triggering else "Unknown hard stop condition."

        _emit_abort(trigger_name, trigger_detail)
        _stderr_hard_stop(trigger_name, trigger_detail)
        sys.exit(1)

    return result

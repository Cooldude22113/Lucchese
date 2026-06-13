"""
observability/startup_validator.py
STAB-005 — Startup validation and state-layer integrity (Rule 15).

Runs once at startup, after the databases are initialised, before the server
accepts traffic. Emits structured entries to the "lucchese.startup" logger.
Hard-stops the process on critical failures; returns a StartupValidationResult on
degraded/OK outcomes. Read-only with respect to the databases and ChromaDB.

Schema truth: the expected tables/columns are imported from storage/sqlite/schema.py
(EXPECTED_*_TABLES) so this validator and the DDL can never drift — there is no
re-declared catalogue here to maintain.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config.paths import CHROMA_PATH, CONVERSATIONS_DB, STATE_DB
from observability.logging_config import configure_startup_logger
from storage.sqlite.schema import EXPECTED_CONVERSATIONS_TABLES, EXPECTED_STATE_TABLES

configure_startup_logger()
_log = logging.getLogger("lucchese.startup")


def _ts() -> str:
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
    overall_status: str
    checks: list
    should_abort: bool
    degraded_components: list
    failed_components: list
    warning_components: list

    @classmethod
    def build(cls, checks: list) -> "StartupValidationResult":
        should_abort = any(
            c.status == "failed" and c.failure_policy == "hard_stop" for c in checks
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

        return cls(
            overall_status=overall,
            checks=checks,
            should_abort=should_abort,
            degraded_components=degraded,
            failed_components=failed,
            warning_components=warnings,
        )


# ── Canonical schema (single source: storage/sqlite/schema.py) ────────────────
CANONICAL_STATE_SCHEMA = EXPECTED_STATE_TABLES
CANONICAL_CONVERSATION_SCHEMA = EXPECTED_CONVERSATIONS_TABLES

# ── Environment variable catalogue ────────────────────────────────────────────
REQUIRED_ENV_VARS: list[str] = ["CHAT_PROVIDER"]
VALID_CHAT_PROVIDERS: set[str] = {"ollama", "claude", "openai"}
PROVIDER_REQUIRED_VARS: dict[str, list[str]] = {
    "claude": ["ANTHROPIC_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
}
OPTIONAL_ENV_VARS: list[str] = [
    "OLLAMA_BASE_URL",
    "CHROMA_PATH",
    "MODEL_FAST",
    "MODEL_DEEP",
    "ELEVENLABS_API_KEY",
    "SHOPIFY_STORE",
    "SHOPIFY_TOKEN",
    "GOOGLE_SHEETS_ID",
]

_STATE_DB_PATH = Path(STATE_DB)
_CONVERSATIONS_DB_PATH = Path(CONVERSATIONS_DB)
_CHROMA_PATH = CHROMA_PATH
_CHROMADB_TIMEOUT_SECONDS = 5


# ── Log helpers ───────────────────────────────────────────────────────────────

def _emit_check(result: CheckResult) -> None:
    level = (
        logging.WARNING
        if result.status in ("warning", "degraded", "failed", "skipped")
        else logging.INFO
    )
    _log.log(level, json.dumps({
        "logger": "lucchese.startup",
        "event": "startup_check",
        "check": result.check_name,
        "status": result.status,
        "failure_policy": result.failure_policy,
        "detail": result.detail,
        "timestamp": _ts(),
    }))


def _emit_aggregate(result: StartupValidationResult, checks_run: int, checks_skipped: int) -> None:
    level = logging.WARNING if result.overall_status != "ok" else logging.INFO
    _log.log(level, json.dumps({
        "logger": "lucchese.startup",
        "event": "startup_validation_complete",
        "overall_status": result.overall_status,
        "should_abort": result.should_abort,
        "degraded_components": result.degraded_components,
        "failed_components": result.failed_components,
        "warning_components": result.warning_components,
        "checks_run": checks_run,
        "checks_skipped": checks_skipped,
        "timestamp": _ts(),
    }))


def _emit_abort(check_name: str, detail: str) -> None:
    _log.error(json.dumps({
        "logger": "lucchese.startup",
        "event": "startup_aborted",
        "reason": check_name,
        "detail": detail,
        "timestamp": _ts(),
    }))


def _stderr_hard_stop(check_name: str, detail: str) -> None:
    print(
        f"\nLUCCHESE STARTUP FAILED\n"
        f"Check: {check_name}\n"
        f"Reason: {detail}\n"
        f"The server will not start. Resolve the above before restarting.\n",
        file=sys.stderr,
        flush=True,
    )


def _skip(check_name: str, reason: str) -> CheckResult:
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
    """Check 1 — environment variable validation. Credential values are never logged."""
    results: list[CheckResult] = []

    for var in REQUIRED_ENV_VARS:
        value = os.getenv(var)
        if value is None or value.strip() == "":
            r = CheckResult(f"env.{var}", "failed",
                            f"Required environment variable '{var}' is absent or empty.",
                            "hard_stop")
        else:
            r = CheckResult(f"env.{var}", "ok", f"'{var}' is present.", "hard_stop")
        _emit_check(r)
        results.append(r)

    provider_value = os.getenv("CHAT_PROVIDER", "").strip().lower()
    if provider_value and provider_value not in VALID_CHAT_PROVIDERS:
        r = CheckResult("env.CHAT_PROVIDER.value", "failed",
                        f"CHAT_PROVIDER value '{provider_value}' is not in the allowed set: "
                        f"{sorted(VALID_CHAT_PROVIDERS)}.", "hard_stop")
        _emit_check(r)
        results.append(r)
    elif provider_value in VALID_CHAT_PROVIDERS:
        r = CheckResult("env.CHAT_PROVIDER.value", "ok",
                        f"CHAT_PROVIDER='{provider_value}' is a valid provider.", "hard_stop")
        _emit_check(r)
        results.append(r)

    if provider_value in PROVIDER_REQUIRED_VARS:
        for var in PROVIDER_REQUIRED_VARS[provider_value]:
            value = os.getenv(var)
            if value is None or value.strip() == "":
                r = CheckResult(f"env.{var}", "failed",
                                f"CHAT_PROVIDER='{provider_value}' requires '{var}', "
                                f"which is absent or empty.", "hard_stop")
            else:
                r = CheckResult(f"env.{var}", "ok",
                                f"'{var}' is present (value not logged).", "hard_stop")
            _emit_check(r)
            results.append(r)

    for var in OPTIONAL_ENV_VARS:
        value = os.getenv(var)
        if value is None or value.strip() == "":
            defaults = {
                "OLLAMA_BASE_URL": "http://localhost:11434",
                "CHROMA_PATH": "./chroma_db",
                "MODEL_FAST": "gemma2:27b",
            }
            default_note = f" (hardcoded default: '{defaults[var]}')" if var in defaults else ""
            r = CheckResult(f"env.{var}", "warning",
                            f"Optional variable '{var}' is absent{default_note}.", "warning")
        else:
            r = CheckResult(f"env.{var}", "ok",
                            f"Optional variable '{var}' is present.", "warning")
        _emit_check(r)
        results.append(r)

    return results


def check_sqlite_connectivity(db_path: Path, check_name: str) -> CheckResult:
    """Check 2 — open a read-only connection to confirm the DB is accessible."""
    try:
        uri = f"file:{db_path.resolve()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.close()
        r = CheckResult(check_name, "ok",
                        f"Database '{db_path}' opened successfully (read-only).", "hard_stop")
    except Exception as exc:
        r = CheckResult(check_name, "failed",
                        f"Cannot open database '{db_path}': {exc}", "hard_stop")
    _emit_check(r)
    return r


def check_required_tables(
    db_path: Path,
    expected_tables: dict[str, list[str]],
    check_name_prefix: str,
) -> list[CheckResult]:
    """Check 3 — required tables present (PRAGMA table_list)."""
    results: list[CheckResult] = []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("PRAGMA table_list").fetchall()
        live_tables = {row["name"] for row in rows}
        conn.close()
    except Exception as exc:
        r = CheckResult(f"{check_name_prefix}.table_list", "failed",
                        f"PRAGMA table_list failed on '{db_path}': {exc}", "hard_stop")
        _emit_check(r)
        results.append(r)
        return results

    for table_name in expected_tables:
        if table_name in live_tables:
            r = CheckResult(f"{check_name_prefix}.table.{table_name}", "ok",
                            f"Table '{table_name}' exists in '{db_path}'.", "hard_stop")
        else:
            r = CheckResult(f"{check_name_prefix}.table.{table_name}", "failed",
                            f"Required table '{table_name}' is missing from '{db_path}'.",
                            "hard_stop")
        _emit_check(r)
        results.append(r)

    return results


def check_state_schema(
    db_path: Path,
    canonical_schema: dict[str, list[str]],
    tables_present: set[str],
    check_name_prefix: str,
) -> list[CheckResult]:
    """Check 4 — per-table column integrity. Missing column = hard stop; extra = warning."""
    results: list[CheckResult] = []

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    except Exception as exc:
        r = CheckResult(f"{check_name_prefix}.schema_open", "failed",
                        f"Cannot open '{db_path}' for schema check: {exc}", "hard_stop")
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
            r = CheckResult(check_name, "failed",
                            f"PRAGMA table_info({table_name}) failed: {exc}", "hard_stop")
            _emit_check(r)
            results.append(r)
            continue

        expected_set = set(expected_columns)
        missing = expected_set - live_columns
        extra = live_columns - expected_set

        if missing:
            r = CheckResult(check_name, "failed",
                            f"Schema drift in '{table_name}': expected columns absent: "
                            f"{sorted(missing)}.", "hard_stop")
        elif extra:
            r = CheckResult(check_name, "warning",
                            f"'{table_name}' has extra columns beyond canonical schema "
                            f"(not drift — may be intentional additions): {sorted(extra)}.",
                            "warning")
        else:
            r = CheckResult(check_name, "ok",
                            f"'{table_name}' schema matches canonical definition.", "hard_stop")

        _emit_check(r)
        results.append(r)

    conn.close()
    return results


def check_profile_state_row(db_path: Path, schema_ok: bool) -> CheckResult:
    """Check 5 — profile_state row presence. Absent = warning; query failure = hard stop."""
    check_name = "state.profile_state.row_presence"

    if not schema_ok:
        return _skip(check_name, "profile_state schema check did not pass")

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT id FROM profile_state WHERE id = 1").fetchone()
        conn.close()
    except Exception as exc:
        r = CheckResult(check_name, "failed",
                        f"profile_state row query failed unexpectedly: {exc}", "hard_stop")
        _emit_check(r)
        return r

    if row is None:
        r = CheckResult(check_name, "warning",
                        "profile_state row is absent (tier1_status: not_seeded). "
                        "Tier 1 context will be empty at inference time. "
                        "Populate via PATCH /state/profile or seed_profile.py.", "warning")
    else:
        r = CheckResult(check_name, "ok",
                        "profile_state row (id=1) is present.", "hard_stop")

    _emit_check(r)
    return r


def check_chromadb_connectivity(chroma_path: str) -> CheckResult:
    """Check 6 — ChromaDB connectivity (PersistentClient). Unreachable = degraded start."""
    check_name = "chromadb.connectivity"
    result_container: list[Optional[CheckResult]] = [None]

    def _probe():
        try:
            import chromadb as _chromadb

            client = _chromadb.PersistentClient(path=chroma_path)
            client.list_collections()
            result_container[0] = CheckResult(check_name, "ok",
                                              f"ChromaDB reachable at path '{chroma_path}'.",
                                              "degraded_start")
        except Exception as exc:
            result_container[0] = CheckResult(check_name, "degraded",
                                              f"ChromaDB unavailable at '{chroma_path}': {exc}",
                                              "degraded_start")

    thread = threading.Thread(target=_probe, daemon=True)
    thread.start()
    thread.join(timeout=_CHROMADB_TIMEOUT_SECONDS)

    if thread.is_alive():
        r = CheckResult(check_name, "degraded",
                        f"ChromaDB connectivity check timed out after "
                        f"{_CHROMADB_TIMEOUT_SECONDS}s at path '{chroma_path}'. "
                        "Memory retrieval will fail at inference time.", "degraded_start")
    elif result_container[0] is None:
        r = CheckResult(check_name, "degraded",
                        "ChromaDB probe returned no result (unexpected).", "degraded_start")
    else:
        r = result_container[0]

    _emit_check(r)
    return r


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run_startup_validation() -> StartupValidationResult:
    """Run all checks in order, enforce failure policy, and (on hard stop) sys.exit(1)."""
    all_checks: list[CheckResult] = []
    checks_skipped = 0

    _log.info(json.dumps({
        "logger": "lucchese.startup",
        "event": "startup_validation_begin",
        "timestamp": _ts(),
    }))

    # 1. Environment
    all_checks.extend(check_environment())

    # 2. SQLite connectivity
    state_conn_result = check_sqlite_connectivity(_STATE_DB_PATH, "sqlite.state_db.connectivity")
    all_checks.append(state_conn_result)
    state_db_ok = state_conn_result.status == "ok"

    conv_conn_result = check_sqlite_connectivity(
        _CONVERSATIONS_DB_PATH, "sqlite.conversations_db.connectivity"
    )
    all_checks.append(conv_conn_result)
    conv_db_ok = conv_conn_result.status == "ok"

    # 3. Required tables present
    state_tables_present: set[str] = set()
    conv_tables_present: set[str] = set()

    if state_db_ok:
        state_table_results = check_required_tables(
            _STATE_DB_PATH, CANONICAL_STATE_SCHEMA, "sqlite.state_db"
        )
        all_checks.extend(state_table_results)
        for r in state_table_results:
            if r.status == "ok":
                parts = r.check_name.split(".")
                if len(parts) >= 4:
                    state_tables_present.add(parts[3])
    else:
        checks_skipped += len(CANONICAL_STATE_SCHEMA)
        for table_name in CANONICAL_STATE_SCHEMA:
            all_checks.append(_skip(f"sqlite.state_db.table.{table_name}",
                                    "state DB connectivity failed"))

    if conv_db_ok:
        conv_table_results = check_required_tables(
            _CONVERSATIONS_DB_PATH, CANONICAL_CONVERSATION_SCHEMA, "sqlite.conversations_db"
        )
        all_checks.extend(conv_table_results)
        for r in conv_table_results:
            if r.status == "ok":
                parts = r.check_name.split(".")
                if len(parts) >= 4:
                    conv_tables_present.add(parts[3])
    else:
        checks_skipped += len(CANONICAL_CONVERSATION_SCHEMA)
        for table_name in CANONICAL_CONVERSATION_SCHEMA:
            all_checks.append(_skip(f"sqlite.conversations_db.table.{table_name}",
                                    "conversations DB connectivity failed"))

    # 4. Schema integrity
    if state_db_ok:
        all_checks.extend(check_state_schema(
            _STATE_DB_PATH, CANONICAL_STATE_SCHEMA, state_tables_present, "sqlite.state_db"
        ))
    else:
        checks_skipped += len(CANONICAL_STATE_SCHEMA)
        for table_name in CANONICAL_STATE_SCHEMA:
            all_checks.append(_skip(f"sqlite.state_db.schema.{table_name}",
                                    "state DB connectivity failed"))

    if conv_db_ok:
        all_checks.extend(check_state_schema(
            _CONVERSATIONS_DB_PATH, CANONICAL_CONVERSATION_SCHEMA,
            conv_tables_present, "sqlite.conversations_db"
        ))
    else:
        checks_skipped += len(CANONICAL_CONVERSATION_SCHEMA)
        for table_name in CANONICAL_CONVERSATION_SCHEMA:
            all_checks.append(_skip(f"sqlite.conversations_db.schema.{table_name}",
                                    "conversations DB connectivity failed"))

    # 5. profile_state row presence
    profile_schema_ok = any(
        r.check_name == "sqlite.state_db.schema.profile_state" and r.status == "ok"
        for r in all_checks
    )
    if state_db_ok:
        all_checks.append(check_profile_state_row(_STATE_DB_PATH, profile_schema_ok))
    else:
        checks_skipped += 1
        all_checks.append(_skip("state.profile_state.row_presence",
                                "state DB connectivity failed"))

    # 6. ChromaDB connectivity
    all_checks.append(check_chromadb_connectivity(_CHROMA_PATH))

    # Aggregate
    checks_run = len(all_checks) - checks_skipped
    result = StartupValidationResult.build(all_checks)
    _emit_aggregate(result, checks_run, checks_skipped)

    # Hard stop enforcement
    if result.should_abort:
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

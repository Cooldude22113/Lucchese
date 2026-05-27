# routes/state.py

import json
import logging
import sqlite3
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
from contextlib import contextmanager
from typing import Literal



router = APIRouter(prefix="/state", tags=["state"])

DB_PATH = Path("lucchese_state.db")

log = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc).isoformat()

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()



def apply_migrations(conn):
    """
    Idempotent schema migration for profile_state.
    Adds confirmed and field_meta columns if absent.
    Called from init_state_db() after the CREATE TABLE block.

    Raises on PRAGMA failure — a broken database should not start silently.
    """
    try:
        rows = conn.execute("PRAGMA table_info(profile_state)").fetchall()
    except Exception as e:
        log.error("apply_migrations: PRAGMA table_info(profile_state) failed: %s", e)
        raise

    existing_columns = {row["name"] for row in rows}
    new_columns = {
        "active_projects": "TEXT",
        "current_business": "TEXT",
        "training_focus": "TEXT",
        "current_priorities": "TEXT",
        "system_goal": "TEXT",
        "memory_status": "TEXT",
        "historical_context": "TEXT",
        "personality_mode": "TEXT",
    }
    for name, col_type in new_columns.items():
        if name not in existing_columns:
            conn.execute(f"ALTER TABLE profile_state ADD COLUMN {name} {col_type}")

    if "confirmed" not in existing_columns:
        conn.execute(
            "ALTER TABLE profile_state ADD COLUMN confirmed INTEGER NOT NULL DEFAULT 0"
        )
        log.info("apply_migrations: added column 'confirmed' to profile_state")

    if "field_meta" not in existing_columns:
        conn.execute(
            "ALTER TABLE profile_state ADD COLUMN field_meta TEXT"
        )
        log.info("apply_migrations: added column 'field_meta' to profile_state")


def init_state_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'active',
            current_focus TEXT,
            next_action TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            priority TEXT NOT NULL DEFAULT 'medium',
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );

        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            decision TEXT NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );

        CREATE TABLE IF NOT EXISTS blockers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            blocker TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );

        CREATE TABLE IF NOT EXISTS daily_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            active_project TEXT,
            active_mode TEXT,
            current_focus TEXT,
            last_summary TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS profile_state (
            id               INTEGER PRIMARY KEY CHECK (id = 1),
            age              INTEGER,
            active_course    TEXT,
            course_status    TEXT,
            primary_project  TEXT,
            active_projects     TEXT,
            current_business    TEXT,
            training_focus      TEXT,
            current_priorities  TEXT,
            system_goal         TEXT,
            memory_status       TEXT,
            historical_context  TEXT,
            personality_mode    TEXT,
            focus_area       TEXT,
            confirmed        INTEGER NOT NULL DEFAULT 0,
            field_meta       TEXT,
            updated_at       TEXT NOT NULL
        );
        """)
        # Migration: adds confirmed + field_meta to existing installs that
        # pre-date this schema update. Idempotent — skips columns already present.
        apply_migrations(conn)


def get_profile_state() -> dict | None:
    """
    Read the single profile_state row.
    Returns a dict of all columns, or None if the row has never been written.
    """
    with db() as conn:
        row = conn.execute("SELECT * FROM profile_state WHERE id=1").fetchone()
        return dict(row) if row else None


def _merge_field_meta(existing_json: str | None, incoming: dict | None) -> str | None:
    """
    Merge field_meta at the field level — incoming keys overwrite, existing
    keys not present in incoming are preserved.

    Returns serialised JSON string, or None if result is empty.
    """
    if not existing_json:
        existing: dict = {}
    else:
        try:
            existing = json.loads(existing_json)
        except Exception:
            log.warning("_merge_field_meta: field_meta JSON corrupt in DB — resetting to empty")
            existing = {}

    if incoming is None:
        return json.dumps(existing) if existing else None

    merged = {**existing, **incoming}
    return json.dumps(merged) if merged else None


class ProfileIn(BaseModel):
    age:             int | None  = None
    active_course:   str | None  = None
    course_status:   str | None  = None
    primary_project: str | None  = None
    focus_area:      str | None  = None
    active_projects: str | None = None
    current_business: str | None = None
    training_focus: str | None = None
    current_priorities: str | None = None
    system_goal: str | None = None
    memory_status: str | None = None
    historical_context: str | None = None
    personality_mode: str | None = None
    confirmed:       bool | None = None
    field_meta:      dict | None = None  # per-field provenance; merged, not replaced
    clear_fields:    list[str]   = []

class ProjectIn(BaseModel):
    name: str
    current_focus: str | None = None
    next_action: str | None = None

class TaskIn(BaseModel):
    project_id: int | None = None
    title: str
    priority: Literal["low", "medium", "high"] = "medium"
    notes: str | None = None


class DecisionIn(BaseModel):
    project_id: int | None = None
    decision: str
    reason: str | None = None

class BlockerIn(BaseModel):
    project_id: int | None = None
    blocker: str



@router.get("/overview")
def overview():
    with db() as conn:
        projects  = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        tasks     = conn.execute("SELECT * FROM tasks WHERE status='open' ORDER BY id DESC LIMIT 20").fetchall()
        blockers  = conn.execute("SELECT * FROM blockers WHERE status='open' ORDER BY id DESC").fetchall()
        decisions = conn.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT 10").fetchall()

    return {
        "projects":          [dict(r) for r in projects],
        "open_tasks":        [dict(r) for r in tasks],
        "open_blockers":     [dict(r) for r in blockers],
        "recent_decisions":  [dict(r) for r in decisions],
    }


@router.post("/projects")
def create_project(item: ProjectIn):
    t = now()
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO projects (name, current_focus, next_action, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (item.name, item.current_focus, item.next_action, t, t)
        )
    return {"id": cur.lastrowid, "status": "created"}


@router.post("/tasks")
def create_task(item: TaskIn):
    t = now()
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO tasks (project_id, title, priority, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (item.project_id, item.title, item.priority, item.notes, t, t)
        )
    return {"id": cur.lastrowid, "status": "created"}


@router.patch("/tasks/{task_id}/done")
def complete_task(task_id: int):
    with db() as conn:
        cur = conn.execute(
            "UPDATE tasks SET status='done', updated_at=? WHERE id=?",
            (now(), task_id)
        )
    if cur.rowcount == 0:
        raise HTTPException(404, "Task not found")
    return {"status": "done"}


@router.post("/decisions")
def create_decision(item: DecisionIn):
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO decisions (project_id, decision, reason, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (item.project_id, item.decision, item.reason, now())
        )
    return {"id": cur.lastrowid, "status": "created"}


@router.post("/blockers")
def create_blocker(item: BlockerIn):
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO blockers (project_id, blocker, created_at)
            VALUES (?, ?, ?)
            """,
            (item.project_id, item.blocker, now())
        )
    return {"id": cur.lastrowid, "status": "created"}


@router.patch("/blockers/{blocker_id}/resolve")
def resolve_blocker(blocker_id: int):
    with db() as conn:
        cur = conn.execute(
            "UPDATE blockers SET status='resolved', resolved_at=? WHERE id=?",
            (now(), blocker_id)
        )
    if cur.rowcount == 0:
        raise HTTPException(404, "Blocker not found")
    return {"status": "resolved"}


@router.patch("/profile")
def upsert_profile(item: ProfileIn):
    """
    Merge incoming non-null fields over the existing profile_state row.
    Omitted fields are preserved — no clobbering.

    Replaces the previous INSERT OR REPLACE semantics, which wrote NULL for
    every omitted field. This endpoint now reads the current row, merges, and
    writes the complete merged row back.

    field_meta is merged at the field level: incoming field keys overwrite,
    existing field keys not present in the incoming payload are preserved.
    """
    with db() as conn:
        row = conn.execute("SELECT * FROM profile_state WHERE id=1").fetchone()

        if row is None:
            existing: dict = {
                "age": None, "active_course": None, "course_status": None,
                "primary_project": None, "focus_area": None,
                "confirmed": 0, "field_meta": None,
            }
        else:
            existing = dict(row)

        # COALESCE: incoming value wins if not None, otherwise keep existing
        merged_age             = item.age             if item.age             is not None else existing.get("age")
        merged_active_course   = item.active_course   if item.active_course   is not None else existing.get("active_course")
        merged_course_status   = item.course_status   if item.course_status   is not None else existing.get("course_status")
        merged_primary_project = item.primary_project if item.primary_project is not None else existing.get("primary_project")
        merged_focus_area      = item.focus_area      if item.focus_area      is not None else existing.get("focus_area")
        merged_active_projects = item.active_projects if item.active_projects is not None else existing.get("active_projects")
        merged_current_business = item.current_business if item.current_business is not None else existing.get("current_business")
        merged_training_focus = item.training_focus if item.training_focus is not None else existing.get("training_focus")
        merged_current_priorities = item.current_priorities if item.current_priorities is not None else existing.get("current_priorities")
        merged_system_goal = item.system_goal if item.system_goal is not None else existing.get("system_goal")
        merged_memory_status = item.memory_status if item.memory_status is not None else existing.get("memory_status")
        merged_historical_context = item.historical_context if item.historical_context is not None else existing.get("historical_context")
        merged_personality_mode = item.personality_mode if item.personality_mode is not None else existing.get("personality_mode")

        # confirmed: None means preserve existing value
        if item.confirmed is not None:
            merged_confirmed = 1 if item.confirmed else 0
        else:
            merged_confirmed = existing.get("confirmed", 0)

        # field_meta: field-level merge (not blob-level replace)
        merged_field_meta = _merge_field_meta(existing.get("field_meta"), item.field_meta)
        # Apply field clears — explicit nulling of named fields
        CLEARABLE = {
            "age", "active_course", "course_status", "primary_project",
            "focus_area", "active_projects", "current_business", "training_focus",
            "current_priorities", "system_goal", "memory_status",
            "historical_context", "personality_mode",
        }
        for fname in item.clear_fields:
            if fname in CLEARABLE:
                locals()[f"merged_{fname}"] = None
        conn.execute(
            """
            INSERT OR REPLACE INTO profile_state
                (id, age, active_course, course_status, primary_project, focus_area,
                active_projects, current_business, training_focus, current_priorities,
                system_goal, memory_status, historical_context, personality_mode,
                confirmed, field_meta, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                merged_age,
                merged_active_course,
                merged_course_status,
                merged_primary_project,
                merged_focus_area,
                merged_active_projects,
                merged_current_business,
                merged_training_focus,
                merged_current_priorities,
                merged_system_goal,
                merged_memory_status,
                merged_historical_context,
                merged_personality_mode,
                merged_confirmed,
                merged_field_meta,
                now(),
            )
        )

    return {"status": "ok"}


@router.get("/profile")
def get_profile():
    """Return the current profile_state row, or an empty object if unset."""
    with db() as conn:
        row = conn.execute("SELECT * FROM profile_state WHERE id=1").fetchone()
    return dict(row) if row else {}
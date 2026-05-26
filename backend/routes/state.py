# routes/state.py

import sqlite3
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path

router = APIRouter(prefix="/state", tags=["state"])

DB_PATH = Path("lucchese_state.db")

def now():
    return datetime.now(timezone.utc).isoformat()

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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
        """)

class ProjectIn(BaseModel):
    name: str
    current_focus: str | None = None
    next_action: str | None = None

class TaskIn(BaseModel):
    project_id: int | None = None
    title: str
    priority: str = "medium"
    notes: str | None = None

class DecisionIn(BaseModel):
    project_id: int | None = None
    decision: str
    reason: str | None = None

class BlockerIn(BaseModel):
    project_id: int | None = None
    blocker: str

@router.on_event("startup")
def startup():
    init_state_db()

@router.get("/overview")
def overview():
    with db() as conn:
        projects = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        tasks = conn.execute("SELECT * FROM tasks WHERE status='open' ORDER BY id DESC LIMIT 20").fetchall()
        blockers = conn.execute("SELECT * FROM blockers WHERE status='open' ORDER BY id DESC").fetchall()
        decisions = conn.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT 10").fetchall()

    return {
        "projects": [dict(r) for r in projects],
        "open_tasks": [dict(r) for r in tasks],
        "open_blockers": [dict(r) for r in blockers],
        "recent_decisions": [dict(r) for r in decisions],
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
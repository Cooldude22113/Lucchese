"""
api/routes/state_routes.py
Thin HTTP layer for the project/profile state tracker (Rule 2: routes receive,
validate, delegate, respond). All persistence lives in state/**.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas.state import BlockerIn, DecisionIn, ProfileIn, ProjectIn, TaskIn
from state.profile import profile_reader, profile_writer
from state.projects import (
    blocker_writer,
    decision_writer,
    project_reader,
    project_writer,
    task_writer,
)

router = APIRouter(prefix="/state", tags=["state"])

# Columns the profile writer merges, mapped from the request model.
_PROFILE_FIELDS = (
    "age", "active_course", "course_status", "primary_project", "focus_area",
    "active_projects", "current_business", "training_focus",
    "current_priorities", "historical_context",
)


@router.get("/overview")
def overview():
    return project_reader.overview()


@router.post("/projects")
def create_project(item: ProjectIn):
    new_id = project_writer.create_project(item.name, item.current_focus, item.next_action)
    return {"id": new_id, "status": "created"}


@router.post("/tasks")
def create_task(item: TaskIn):
    new_id = task_writer.create_task(item.project_id, item.title, item.priority, item.notes)
    return {"id": new_id, "status": "created"}


@router.patch("/tasks/{task_id}/done")
def complete_task(task_id: int):
    if not task_writer.complete_task(task_id):
        raise HTTPException(404, "Task not found")
    return {"status": "done"}


@router.post("/decisions")
def create_decision(item: DecisionIn):
    new_id = decision_writer.create_decision(item.project_id, item.decision, item.reason)
    return {"id": new_id, "status": "created"}


@router.post("/blockers")
def create_blocker(item: BlockerIn):
    new_id = blocker_writer.create_blocker(item.project_id, item.blocker)
    return {"id": new_id, "status": "created"}


@router.patch("/blockers/{blocker_id}/resolve")
def resolve_blocker(blocker_id: int):
    if not blocker_writer.resolve_blocker(blocker_id):
        raise HTTPException(404, "Blocker not found")
    return {"status": "resolved"}


@router.patch("/profile")
def upsert_profile(item: ProfileIn):
    values = {field: getattr(item, field) for field in _PROFILE_FIELDS}
    return profile_writer.upsert_profile(
        values,
        field_meta=item.field_meta,
        confirmed=item.confirmed,
        clear_fields=item.clear_fields,
    )


@router.get("/profile")
def get_profile():
    return profile_reader.get_profile()

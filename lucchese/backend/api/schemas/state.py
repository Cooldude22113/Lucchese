"""
api/schemas/state.py
Request models for the /state endpoints (Rule: request/response models live in
api/schemas/).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ProfileIn(BaseModel):
    age:                int | None  = None
    active_course:      str | None  = None
    course_status:      str | None  = None
    primary_project:    str | None  = None
    focus_area:         str | None  = None
    active_projects:    str | None  = None
    current_business:   str | None  = None
    training_focus:     str | None  = None
    current_priorities: str | None  = None
    historical_context: str | None  = None
    confirmed:          bool | None = None
    field_meta:         dict | None = None  # per-field provenance; merged, not replaced
    clear_fields:       list[str]   = []


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

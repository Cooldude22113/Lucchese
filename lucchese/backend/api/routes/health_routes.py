"""
api/routes/health_routes.py
Public health check (Rule 2). No auth required.
"""

from __future__ import annotations

from fastapi import APIRouter

from observability.health_checks import health_snapshot

router = APIRouter()


@router.get("/health")
def health():
    """Public health check — returns collection counts."""
    return health_snapshot()

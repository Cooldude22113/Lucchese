"""
api/routes/debug_routes.py
Thin developer/debug endpoint (Rule 2, Rule 17), protected by the admin key.

  GET /debug/memory — raw dump of the knowledge collection
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from inspection.raw_debug_dump import dump_knowledge
from security.admin_auth import verify_admin_key

router = APIRouter()


@router.get("/debug/memory")
def debug_memory(admin_key: str = Depends(verify_admin_key)):
    return dump_knowledge()

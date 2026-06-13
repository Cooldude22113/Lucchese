"""
api/routes/admin_routes.py
Thin admin endpoints (Rule 2), all protected by the X-Admin-Key header (Rule 16).

  GET    /admin/stats      — memory collection counts by source and category
  GET    /admin/recent     — last N ingested facts
  GET    /admin/search     — semantic search across the facts collection
  DELETE /admin/memory     — delete all entries from a given source
  POST   /admin/summarise  — collapse memory into per-category summaries
  GET    /admin/summaries  — list generated summaries
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from application.orchestration.admin_flow import run_summarise
from inspection.admin_stats import admin_stats
from inspection.recent_memory import recent_facts
from inspection.semantic_search import search_facts
from memory.inspection.memory_delete import delete_by_source
from memory.inspection.summary_inspection import list_summaries
from security.admin_auth import verify_admin_key

router = APIRouter()


@router.get("/admin/stats")
def stats(admin_key: str = Depends(verify_admin_key)):
    return admin_stats()


@router.get("/admin/recent")
def recent(limit: int = 20, admin_key: str = Depends(verify_admin_key)):
    return recent_facts(limit)


@router.get("/admin/search")
def search(q: str = "", n: int = 10, admin_key: str = Depends(verify_admin_key)):
    if not q.strip():
        raise HTTPException(400, "Query parameter 'q' is required")
    return search_facts(q, n)


@router.delete("/admin/memory")
def delete_memory(source: str = "", admin_key: str = Depends(verify_admin_key)):
    if not source.strip():
        raise HTTPException(400, "Source parameter is required")
    deleted = delete_by_source(source)
    return {"deleted": deleted, "source": source}


@router.post("/admin/summarise")
async def summarise(admin_key: str = Depends(verify_admin_key)):
    return await run_summarise()


@router.get("/admin/summaries")
def summaries(admin_key: str = Depends(verify_admin_key)):
    return list_summaries()

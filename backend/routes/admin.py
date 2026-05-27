"""
routes/admin.py
───────────────
Admin and diagnostic endpoints — all protected by X-Admin-Key header.

  GET    /admin/stats       — memory collection counts by source and category
  GET    /admin/recent      — last N ingested facts
  GET    /admin/search      — semantic search across facts collection
  DELETE /admin/memory      — delete all entries from a given source
  POST   /admin/summarise   — collapse memory clusters into per-category summaries
  GET    /admin/summaries   — list all generated summaries
  GET    /debug/memory      — raw knowledge collection dump (dev tool)
  GET    /health            — collection counts, no auth required
"""

import httpx
from collections import defaultdict
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Header
from routes.config import verify_admin_key, OLLAMA_URL, MODEL_FAST
from routes.memory import col_knowledge, col_facts, col_style, col_summaries, col_documents


router = APIRouter()

    
# ── GET /admin/stats ──────────────────────────────────────────────────────────
@router.get("/admin/stats")
def admin_stats(admin_key: str = Depends(verify_admin_key)):
    stats = {}
    for col, name in [
        (col_knowledge, "knowledge"),
        (col_facts,     "facts"),
        (col_style,     "style"),
    ]:
        source_counts   = {}
        category_counts = {}
        offset = 0
        batch  = 500

        while True:
            results = col.get(
                include=["metadatas"],
                limit=batch,
                offset=offset,
            )
            metas = results["metadatas"]
            if not metas:
                break
            for m in metas:
                src = m.get("source", "unknown")
                cat = m.get("category", "general")
                source_counts[src]   = source_counts.get(src, 0) + 1
                category_counts[cat] = category_counts.get(cat, 0) + 1
            offset += batch

        stats[name] = {
            "total":       col.count(),
            "by_source":   source_counts,
            "by_category": category_counts,
        }
    return stats


# ── GET /admin/recent ─────────────────────────────────────────────────────────
@router.get("/admin/recent")
def admin_recent(limit: int = 20, admin_key: str = Depends(verify_admin_key)):
    """
    Most recently ingested facts, sorted by created_at descending.
    Used by the AdminPanel recent tab.
    """
    results = col_facts.get(include=["documents", "metadatas"], limit=500)
    items = [
        {
            "text":       doc[:120],
            "source":     meta.get("source", "unknown"),
            "category":   meta.get("category", "general"),
            "created_at": meta.get("created_at", ""),
            "conv_id":    meta.get("conv_id", ""),
        }
        for doc, meta in zip(results["documents"], results["metadatas"])
    ]
    items.sort(key=lambda x: x["created_at"] or "", reverse=True)
    return items[:limit]


# ── GET /admin/search ─────────────────────────────────────────────────────────
@router.get("/admin/search")
def admin_search(q: str = "", n: int = 10, admin_key: str = Depends(verify_admin_key)):
    if not q.strip():
        raise HTTPException(400, "Query parameter 'q' is required")    
    """
    Semantic search across the facts collection.
    Returns up to n results with relevance scores.
    """
    results = col_facts.query(
        query_texts=[q],
        n_results=n,
        include=["documents", "metadatas", "distances"]
    )
    return [
        {
            "text":       doc[:200],
            "source":     meta.get("source", "unknown"),
            "category":   meta.get("category", "general"),
            "created_at": meta.get("created_at", ""),
            "relevance":  round(1 / (1 + dist), 3),
        }
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ]


# ── DELETE /admin/memory ──────────────────────────────────────────────────────
@router.delete("/admin/memory")
def admin_delete_memory(source: str = "", admin_key: str = Depends(verify_admin_key)):
    if not source.strip():
        raise HTTPException(400, "Source parameter is required")
    """
    Delete all memory entries from a given source across all collections.
    e.g. DELETE /admin/memory?source=lucchese
    """
    deleted = 0
    for col in col_knowledge, col_facts, col_style:
        try:
            results = col.get(where={"source": source})
            if results["ids"]:
                col.delete(ids=results["ids"])
                deleted += len(results["ids"])
        except Exception as e:
            print(f"admin_delete_memory error: {e}")
    return {"deleted": deleted, "source": source}


# ── POST /admin/summarise ─────────────────────────────────────────────────────
@router.post("/admin/summarise")
async def admin_summarise(admin_key: str = Depends(verify_admin_key)):
    """
    Groups all facts and knowledge by category, then uses the LLM to generate
    a dense per-category summary. Summaries are upserted into col_summaries
    (one entry per category) and used in the RAG system prompt.

    Skips categories with fewer than MIN_ENTRIES entries — not enough signal yet.
    """
    MIN_ENTRIES = 5
    now         = datetime.now(timezone.utc).isoformat()
    results_log = {}

    # Collect all docs from facts + knowledge
    all_docs = []
    for col, label in [
        (col_facts,     "facts"),
        (col_knowledge, "knowledge"),
    ]:
        try:
            results = col.get(include=["documents", "metadatas"])
            for doc, meta in zip(results["documents"], results["metadatas"]):
                if doc.strip():
                    all_docs.append({
                        "text":     doc.strip(),
                        "category": meta.get("category", "general"),
                    })
        except Exception as e:
            print(f"Summarise collect error ({label}): {e}")
            results_log[label] = f"error: {e}"

    # Group by category
    by_category: dict[str, list[str]] = defaultdict(list)
    for d in all_docs:
        by_category[d["category"]].append(d["text"])

    # Summarise each category
    for category, texts in by_category.items():
        if len(texts) < MIN_ENTRIES:
            results_log[category] = f"skipped ({len(texts)} entries, need {MIN_ENTRIES})"
            continue

        sample   = texts[:15]   # cap to avoid huge prompts
        combined = "\n\n---\n\n".join(sample)

        prompt = f"""You are summarising Alex Hammond's memory about the topic: "{category}".

The following are real things Alex has said or discussed in past conversations.
Write a dense, coherent summary of everything you know about Alex in relation to this topic.
Include specific details, preferences, history, goals, and any recurring themes.
Write it as a factual third-person profile, like a knowledgeable assistant briefing someone about Alex.
Do not include generic filler — only specific, useful information.
Keep it under 400 words.

--- Memory entries ---
{combined}
---

Summary:"""

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                res = await client.post(
                    OLLAMA_URL,
                    json={
                        "model":    MODEL_FAST,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream":   False,
                    }
                )
            summary_text = res.json()["message"]["content"].strip()

            col_summaries.upsert(
                ids       = [f"summary_{category}"],
                documents = [summary_text],
                metadatas = [{
                    "category":     category,
                    "entry_count":  str(len(texts)),
                    "last_updated": now,
                    "type":         "summary",
                }]
            )
            results_log[category] = f"ok ({len(texts)} entries summarised)"
            print(f"Summarised: {category} ({len(texts)} entries)")

        except Exception as e:
            print(f"Summarise error ({category}): {e}")
            results_log[category] = f"error: {e}"

    return {"summarised": results_log, "total_categories": len(results_log)}


# ── GET /admin/summaries ──────────────────────────────────────────────────────
@router.get("/admin/summaries")
def admin_summaries(admin_key: str = Depends(verify_admin_key)):
    """List all generated summaries, sorted by entry count descending."""
    try:
        results = col_summaries.get(include=["documents", "metadatas"])
        items = [
            {
                "category":     meta.get("category"),
                "entry_count":  meta.get("entry_count"),
                "last_updated": meta.get("last_updated"),
                "summary":      doc,
            }
            for doc, meta in zip(results["documents"], results["metadatas"])
        ]
        items.sort(key=lambda x: int(x["entry_count"] or 0), reverse=True)
        return items
    except Exception as e:
        return {"error": str(e)}


# ── GET /debug/memory ─────────────────────────────────────────────────────────
@router.get("/debug/memory")
def debug_memory(admin_key: str = Depends(verify_admin_key)):
    """
    Raw dump of the knowledge collection — first 100 chars of each entry,
    sorted by created_at. Dev tool for inspecting what's been ingested.
    """
    results = col_knowledge.get(include=["documents", "metadatas"])
    items = [
        {
            "text":       doc[:100],
            "created_at": meta.get("created_at"),
            "source":     meta.get("source"),
            "type":       meta.get("type"),
        }
        for doc, meta in zip(results["documents"], results["metadatas"])
    ]
    items.sort(key=lambda x: x["created_at"] or "", reverse=True)
    return items

"""
application/orchestration/admin_flow.py
Admin summarise workflow (Rule 3).

Thin orchestration over the memory summarisation routine; returns the response
shape the admin route hands back.
"""

from __future__ import annotations

from memory.processing.summarisation import summarise_all


async def run_summarise() -> dict:
    """Run the per-category summarisation and report the result."""
    results_log = await summarise_all()
    return {"summarised": results_log, "total_categories": len(results_log)}

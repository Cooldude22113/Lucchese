"""
application/services/import_service.py
Reusable import actions (Rule 4).

Stable entrypoints that routes, the orchestration flow, and the CLI script all call,
hiding the ingestion pipeline behind a thin facade. The actual multi-step work lives
in ingestion/pipelines; this just exposes it as callable actions.

The pipeline is synchronous and IO/CPU bound, so run_import offloads it to a worker
thread to avoid blocking the event loop when called from an async route.
"""

from __future__ import annotations

import asyncio

from ingestion.pipelines.import_pipeline import run_import as _run_import_sync
from ingestion.status.import_status import import_status as _import_status


async def run_import(source: str = "all", dry_run: bool = False) -> dict:
    """Run an import for a source ('chatgpt' | 'grok' | 'all'); return the report."""
    return await asyncio.to_thread(_run_import_sync, source, dry_run)


def import_status() -> dict:
    """Return current store counts and recent import-run history."""
    return _import_status()

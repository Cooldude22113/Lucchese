"""
application/orchestration/import_flow.py
Import workflow (Rule 3): prepare runtime, run the import, report.

Coordinates the user-facing import operation: ensure the runtime dirs exist and the
canonical store schema is initialised, log start/finish, then delegate to the import
service. Owns the ordering, not the implementation.
"""

from __future__ import annotations

import logging

from application.services import import_service
from config.paths import ensure_runtime_dirs
from storage.sqlite.conversation_store_schema import init_conversation_store_db

logger = logging.getLogger(__name__)


async def run_import_flow(source: str = "all", dry_run: bool = False) -> dict:
    """Ensure storage is ready, run the import, and return the report."""
    ensure_runtime_dirs()
    init_conversation_store_db()
    logger.info("Starting import flow: source=%s dry_run=%s", source, dry_run)
    report = await import_service.run_import(source=source, dry_run=dry_run)
    totals = report.get("totals", {})
    logger.info(
        "Import flow complete: source=%s conversations=%s messages=%s errors=%s",
        source,
        totals.get("conversations_imported"),
        totals.get("messages_imported"),
        totals.get("errors"),
    )
    return report

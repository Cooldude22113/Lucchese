"""
ingestion/pipelines/import_pipeline.py
Top-level import pipeline (Rule 8 + Rule 3).

For a requested source ∈ {chatgpt, grok, all}: stream raw items from the source,
parse each into a ParsedConversation, and persist it via conversation_pipeline —
all under one import_runs bookkeeping row. Already-imported conversations are
skipped (idempotency), per-conversation failures are captured without aborting the
run, and the result is an ImportReport dict.

Dry-run mode parses and tallies what WOULD be written without touching the store.
"""

from __future__ import annotations

import logging

from config.ingestion_settings import SUPPORTED_SOURCES
from ingestion.parsing import chatgpt_parser, grok_parser
from ingestion.parsing.normalized_models import ParsedConversation
from ingestion.pipelines.conversation_pipeline import count_only, persist_conversation
from ingestion.sources import chatgpt_source, grok_source
from ingestion.status.import_job import ImportJob
from ingestion.status.import_report import ImportReport
from storage.files import import_store
from storage.sqlite.repositories.conversation_store import conversations as conversations_repo
from storage.sqlite.repositories.conversation_store import import_runs as import_runs_repo

logger = logging.getLogger(__name__)

# source name → (raw-item iterator, parse function)
_SOURCES = {
    "chatgpt": (chatgpt_source.iter_conversations, chatgpt_parser.parse_conversation),
    "grok": (grok_source.iter_conversations, grok_parser.parse_conversation),
}


def run_import(source: str = "all", dry_run: bool = False) -> dict:
    """Import one or all sources; return the ImportReport dict."""
    targets = _resolve_targets(source)
    job = ImportJob(source=source, dry_run=dry_run)

    files = [str(p) for src in targets for p in import_store.list_raw_files(src)]
    run_id = None if dry_run else import_runs_repo.start(source, files)

    for src in targets:
        _import_source(src, job)

    report = ImportReport(job).to_dict()
    if run_id is not None:
        import_runs_repo.finish(
            run_id,
            conversations_imported=job.conversations_imported,
            messages_imported=job.messages_imported,
            errors=job.error_count,
            report=report,
        )
    logger.info(
        "Import finished: source=%s dry_run=%s conversations=%d messages=%d errors=%d",
        source, dry_run, job.conversations_imported, job.messages_imported, job.error_count,
    )
    return report


def _import_source(src: str, job: ImportJob) -> None:
    iter_raw, parse = _SOURCES[src]
    tally = job.tally(src)
    already = set() if job.dry_run else conversations_repo.existing_source_ids(src)

    for raw in iter_raw():
        tally.conversations_seen += 1
        parsed: ParsedConversation | None = None
        source_id = None
        try:
            parsed = parse(raw)
            source_id = parsed.source_conversation_id
            if not job.dry_run and source_id in already:
                tally.conversations_skipped += 1
                continue
            if job.dry_run:
                count_only(parsed, tally)
            else:
                persist_conversation(parsed, tally)
                already.add(source_id)
        except Exception as exc:  # noqa: BLE001 — capture per-item, keep going
            logger.warning("Failed to import %s conversation %s: %s", src, source_id, exc)
            job.errors.record(src, source_id, exc)


def _resolve_targets(source: str) -> list[str]:
    if source == "all":
        return list(SUPPORTED_SOURCES)
    if source in SUPPORTED_SOURCES:
        return [source]
    raise ValueError(
        f"Unknown import source {source!r}; expected one of {('all', *SUPPORTED_SOURCES)}"
    )

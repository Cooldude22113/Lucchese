"""
ingestion/status/import_report.py
Turn a finished ImportJob into a serialisable report dict (bookkeeping).

The report is what the service/route/script hand back and what import_runs.report
stores. Pure transformation — no I/O.
"""

from __future__ import annotations

from dataclasses import asdict

from ingestion.status.import_job import ImportJob


class ImportReport:
    """Builds the response dict for a completed import job."""

    def __init__(self, job: ImportJob):
        self.job = job

    def to_dict(self) -> dict:
        job = self.job
        return {
            "source": job.source,
            "dry_run": job.dry_run,
            "totals": {
                "conversations_imported": job.conversations_imported,
                "messages_imported": job.messages_imported,
                "errors": job.error_count,
            },
            "by_source": {src: asdict(tally) for src, tally in job.tallies.items()},
            "errors": job.errors.to_list(),
        }

"""
ingestion/status/import_job.py
Mutable per-run accumulator for an import (bookkeeping).

The import pipeline creates one ImportJob, feeds it per-conversation outcomes, and
hands it to ImportReport at the end. Keeps running tallies out of the pipeline's
control flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ingestion.status.import_errors import ImportErrors


@dataclass
class SourceTally:
    conversations_seen: int = 0
    conversations_imported: int = 0
    conversations_skipped: int = 0
    conversations_empty: int = 0
    messages_imported: int = 0
    tool_calls: int = 0
    web_searches: int = 0
    search_results: int = 0
    attachments: int = 0
    reasoning_traces: int = 0


@dataclass
class ImportJob:
    source: str                                   # 'chatgpt' | 'grok' | 'all'
    dry_run: bool = False
    tallies: dict[str, SourceTally] = field(default_factory=dict)
    errors: ImportErrors = field(default_factory=ImportErrors)

    def tally(self, source: str) -> SourceTally:
        """Get (creating if needed) the running tally for a single source."""
        return self.tallies.setdefault(source, SourceTally())

    @property
    def conversations_imported(self) -> int:
        return sum(t.conversations_imported for t in self.tallies.values())

    @property
    def messages_imported(self) -> int:
        return sum(t.messages_imported for t in self.tallies.values())

    @property
    def error_count(self) -> int:
        return self.errors.count

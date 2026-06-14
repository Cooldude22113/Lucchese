"""
ingestion/status/import_errors.py
Per-item error capture for an import run (Rule 15: observability is first-class).

Lets the pipeline record a single conversation's failure and carry on, instead of
aborting the whole run. The collected entries land in the ImportReport.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ImportErrorEntry:
    source: str
    source_conversation_id: str | None
    error: str


@dataclass
class ImportErrors:
    entries: list[ImportErrorEntry] = field(default_factory=list)

    def record(self, source: str, source_conversation_id: str | None, exc: Exception) -> None:
        """Capture a per-conversation failure."""
        self.entries.append(
            ImportErrorEntry(
                source=source,
                source_conversation_id=source_conversation_id,
                error=f"{type(exc).__name__}: {exc}",
            )
        )

    @property
    def count(self) -> int:
        return len(self.entries)

    def to_list(self) -> list[dict]:
        return [
            {
                "source": e.source,
                "source_conversation_id": e.source_conversation_id,
                "error": e.error,
            }
            for e in self.entries
        ]

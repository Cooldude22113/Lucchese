"""
ingestion/status/import_status.py
Read-only view of what has been imported (Rule 17-ish: read-only visibility).

Backs the GET /admin/import/status endpoint by reading the canonical store: current
conversation/message counts plus the recent import_runs history. No writes.
"""

from __future__ import annotations

from storage.sqlite.repositories.conversation_store import (
    conversations,
    import_runs,
    messages,
)


def import_status() -> dict:
    """Return current store counts and recent import-run history."""
    return {
        "conversations_by_source": conversations.count_by_source(),
        "messages_by_role": messages.count_by_role(),
        "recent_runs": import_runs.recent(limit=10),
    }

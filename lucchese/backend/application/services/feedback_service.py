"""
application/services/feedback_service.py
The two feedback actions: ingest a good exchange, or purge a bad one (Rule 4).
"""

from __future__ import annotations

from memory.ingestion.exchange_ingestor import ingest_exchange
from memory.inspection.memory_delete import purge_conversation


async def record_good(conversation_id: str, user_message: str, assistant_reply: str) -> None:
    """Store a positively-rated exchange into memory."""
    await ingest_exchange(conversation_id, user_message, assistant_reply)


def record_bad(conversation_id: str) -> None:
    """Remove any memory already ingested from a negatively-rated conversation."""
    purge_conversation(conversation_id)

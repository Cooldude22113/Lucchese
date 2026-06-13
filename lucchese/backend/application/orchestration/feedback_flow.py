"""
application/orchestration/feedback_flow.py
Thumbs up/down feedback workflow (Rule 3).

good → ingest the exchange into memory
bad  → purge any memory ingested from this conversation
"""

from __future__ import annotations

from application.services import feedback_service


async def handle_feedback(
    conversation_id: str,
    user_message: str,
    assistant_reply: str,
    rating: str,
) -> dict:
    """Route feedback by rating; returns {"ingested": bool}."""
    if rating == "good":
        await feedback_service.record_good(conversation_id, user_message, assistant_reply)
        return {"ingested": True}

    feedback_service.record_bad(conversation_id)
    return {"ingested": False}

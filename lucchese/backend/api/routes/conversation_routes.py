"""
api/routes/conversation_routes.py
Thin conversation + feedback endpoints (Rule 2).

  GET    /conversations                   — list all conversations
  GET    /conversations/{conversation_id} — messages in a conversation
  DELETE /conversations/{conversation_id} — delete from SQLite + ChromaDB
  POST   /feedback                        — thumbs up/down on a reply
"""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas.conversations import FeedbackRequest
from application.orchestration.feedback_flow import handle_feedback
from application.services import conversation_service

router = APIRouter()


@router.get("/conversations")
def list_conversations():
    return conversation_service.list_all()


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    return conversation_service.get(conversation_id)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    return conversation_service.delete(conversation_id)


@router.post("/feedback")
async def feedback(req: FeedbackRequest):
    return await handle_feedback(
        req.conversation_id, req.user_message, req.assistant_reply, req.rating
    )

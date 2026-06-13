"""
api/schemas/conversations.py
Request models for the conversation/feedback endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel


class FeedbackRequest(BaseModel):
    conversation_id: str
    user_message: str
    assistant_reply: str
    rating: str  # "good" | "bad"

"""
api/schemas/chat.py
Request model for the /chat endpoint.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    history: Optional[list] = []
    conversation_id: Optional[str] = None
    deep: Optional[bool] = False

"""
api/routes/chat_routes.py
Thin chat endpoint (Rule 2). All logic lives in application/orchestration/chat_flow.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.schemas.chat import ChatRequest
from application.orchestration.chat_flow import stream_chat

router = APIRouter()


@router.post("/chat")
async def chat(req: ChatRequest):
    return StreamingResponse(stream_chat(req), media_type="application/x-ndjson")

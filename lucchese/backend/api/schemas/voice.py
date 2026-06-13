"""
api/schemas/voice.py
Request models for the voice endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel


class TTSRequest(BaseModel):
    text: str

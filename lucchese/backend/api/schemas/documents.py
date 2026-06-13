"""
api/schemas/documents.py
Request models for the document endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel


class GenerateDocRequest(BaseModel):
    content: str
    title: str = "document"

"""
memory/commands/remember.py
Explicit "remember" command — store a fact the user dictated (Rule 7).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from memory.collections.collection_registry import get_facts
from memory.processing.classification import classify_memory
from memory.processing.deduplication import is_duplicate_memory


async def remember(content: str, conversation_id: str) -> str:
    """Store `content` as an explicit fact unless a near-duplicate already exists."""
    now = datetime.now(timezone.utc).isoformat()
    col_facts = get_facts()

    if is_duplicate_memory(content, col_facts):
        return "I already have that stored."

    col_facts.upsert(
        ids=[f"explicit_fact_{uuid.uuid4().hex[:8]}"],
        documents=[content],
        metadatas=[{
            "source":     "explicit",
            "conv_id":    conversation_id,
            "type":       "fact",
            "category":   await classify_memory(content),
            "created_at": now,
        }],
    )
    return f"Got it, I'll remember that: *{content}*"

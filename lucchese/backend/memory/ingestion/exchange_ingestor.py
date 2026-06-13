"""
memory/ingestion/exchange_ingestor.py
Write a live Lucchese chat exchange into ChromaDB (Rule 8).

Embeds the user message only (assistant text caused embedding contamination).
Knowledge chunks are stored unclassified for reclassify.py to route later; facts
and style are created immediately for live-session use, gated by ingest policy.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from config.memory_settings import FACT_MIN_CHARS, STYLE_MIN_CHARS
from memory.collections.collection_registry import get_facts, get_knowledge, get_style
from memory.ingestion.ingest_policy import should_ingest, strip_preamble
from memory.processing.chunking import chunk_text
from memory.processing.deduplication import is_duplicate_memory


async def ingest_exchange(conversation_id: str, user_msg: str, assistant_reply: str) -> None:
    """Store a user/assistant exchange across the knowledge/facts/style collections."""
    now = datetime.now(timezone.utc).isoformat()
    pair_idx = uuid.uuid4().hex[:8]
    user_text = user_msg.strip()

    if not user_text:
        return

    col_knowledge = get_knowledge()
    col_facts = get_facts()
    col_style = get_style()

    assistant_excerpt = strip_preamble(assistant_reply)[:600]
    assistant_length = len(assistant_reply)

    base_meta = {
        "source":            "lucchese",
        "conv_id":           conversation_id,
        "pair_idx":          pair_idx,
        "type":              "knowledge",
        "created_at":        now,
        "user_text_raw":     user_text,
        "assistant_excerpt": assistant_excerpt,
        "assistant_length":  assistant_length,
        "category":          "unclassified",
        "ontology":          "unclassified",
        "source_type":       "unclassified",
        "primary_tier1":     "unclassified",
        "primary_tier2":     "unclassified",
        "primary_tier3":     "unclassified",
        "secondary_tier1":   "",
        "secondary_tier2":   "",
        "secondary_tier3":   "",
        "is_personal":       "unclassified",
        "engagement":        "unclassified",
        "routing_done":      "false",
    }

    # Embed user_text only.
    for i, chunk in enumerate(chunk_text(user_text)):
        if not is_duplicate_memory(chunk, col_knowledge):
            col_knowledge.upsert(
                ids=[f"lucchese_{conversation_id}_{pair_idx}_{i}"],
                documents=[chunk],
                metadatas=[{**base_meta, "chunk_idx": str(i)}],
            )

    # Facts — intent-gated, not raw length.
    if len(user_text) >= FACT_MIN_CHARS and should_ingest(user_text, assistant_reply):
        if not is_duplicate_memory(user_text, col_facts):
            col_facts.upsert(
                ids=[f"lucchese_fact_{conversation_id}_{pair_idx}"],
                documents=[user_text],
                metadatas=[{
                    **base_meta,
                    "type": "fact",
                    "source_knowledge_id": f"lucchese_{conversation_id}_{pair_idx}_0",
                }],
            )

    # Style — only substantive messages.
    if len(user_text) >= STYLE_MIN_CHARS:
        if not is_duplicate_memory(user_text, col_style):
            col_style.upsert(
                ids=[f"lucchese_style_{conversation_id}_{pair_idx}"],
                documents=[user_text],
                metadatas=[{
                    **base_meta,
                    "type": "style",
                    "source_knowledge_id": f"lucchese_{conversation_id}_{pair_idx}_0",
                }],
            )

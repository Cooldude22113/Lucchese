"""
memory/processing/chunking.py
Sentence-aware text chunking for embedding (Rule 7).
"""

from __future__ import annotations

import re

from config.memory_settings import CHUNK_OVERLAP, CHUNK_SIZE


def chunk_text(text: str) -> list[str]:
    """
    Split text into <=CHUNK_SIZE chunks on sentence boundaries. Sentences longer
    than CHUNK_SIZE are hard-split with CHUNK_OVERLAP overlap.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= CHUNK_SIZE:
            current = (current + " " + sentence).strip()
        else:
            if current:
                chunks.append(current)
            # NOTE: faithful to the original — `current` is intentionally not reset
            # after a hard split; behaviour preserved during migration.
            if len(sentence) > CHUNK_SIZE:
                for i in range(0, len(sentence), CHUNK_SIZE - CHUNK_OVERLAP):
                    part = sentence[i:i + CHUNK_SIZE]
                    if part.strip():
                        chunks.append(part.strip())
            else:
                current = sentence

    if current:
        chunks.append(current)

    return [c for c in chunks if c.strip()]

"""
memory/commands/forget.py
Explicit "forget" command — delete near-matching memories (Rule 7).
"""

from __future__ import annotations

from config.memory_settings import FORGET_MATCH_THRESHOLD
from memory.collections.collection_registry import get_facts, get_knowledge, get_style


async def forget(content: str) -> str:
    """Delete memories within FORGET_MATCH_THRESHOLD of `content` across collections."""
    deleted = 0
    if content:
        for col in (get_facts(), get_knowledge(), get_style()):
            try:
                results = col.query(
                    query_texts=[content],
                    n_results=3,
                    include=["distances"],
                )
                if results["ids"] and results["ids"][0]:
                    for id_, dist in zip(results["ids"][0], results["distances"][0]):
                        if dist < FORGET_MATCH_THRESHOLD:
                            col.delete(ids=[id_])
                            deleted += 1
            except Exception:
                pass

    if deleted:
        return "Done, I've removed that from my memory."
    return "I couldn't find anything close enough to that in my memory to remove."

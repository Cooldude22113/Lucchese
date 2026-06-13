"""
memory/ingestion/ingest_policy.py
Decide whether a live exchange is worth storing, and clean assistant text (Rule 8).

should_ingest is the intent gate used by both the chat flow and the exchange
ingestor; _strip_preamble trims throat-clearing from assistant replies.
"""

from __future__ import annotations

import re


def should_ingest(user_msg: str, assistant_reply: str) -> bool:
    """True if the user message carries personal/intentful signal worth remembering."""
    msg = user_msg.lower().strip()

    if len(msg) < 30:
        return False

    uncertainty = ["i don't know", "i'm not sure", "i can't find", "i don't have"]
    if any(p in assistant_reply.lower() for p in uncertainty):
        return False

    signals = [
        "my ", "i am", "i'm", "we ", "i have", "i've", "i do", "i don't",
        "alex", "ptpreps", "prefer", "always", "never", "usually", "hate",
        "love", "want", "need", "goal", "plan", "think", "believe", "feel",
    ]
    return any(w in msg for w in signals)


def strip_preamble(text: str, min_words: int = 12) -> str:
    """Drop short preamble sentences, returning from the first substantive one."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    for i, s in enumerate(sentences):
        if len(s.split()) >= min_words:
            return " ".join(sentences[i:])
    return text

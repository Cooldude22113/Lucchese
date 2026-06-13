"""
audio/speech/tts_chunks.py
Merge sentences into natural-length speakable chunks (Rule 13).
"""

from __future__ import annotations


def merge_sentences(sentences: list[str], min_len: int = 80) -> list[str]:
    """Greedily merge sentences so each chunk exceeds min_len characters."""
    merged: list[str] = []
    buf = ""
    for s in sentences:
        buf = (buf + " " + s).strip()
        if len(buf) > min_len:
            merged.append(buf)
            buf = ""
    if buf:
        merged.append(buf)
    return merged

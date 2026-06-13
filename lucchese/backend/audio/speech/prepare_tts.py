"""
audio/speech/prepare_tts.py
Clean and segment reply text for TTS (Rule 13).
"""

from __future__ import annotations

import re

from audio.speech.tts_chunks import merge_sentences


def prepare_tts_chunks(text: str) -> list[str]:
    """
    Strip non-latin characters (emojis etc), split on sentence boundaries, then
    merge into natural-length chunks (>80 chars) for ElevenLabs.
    """
    clean = re.sub(r"[^\x00-\x7FÀ-ɏḀ-ỿ]+", " ", text).strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean) if s.strip()]
    return merge_sentences(sentences, min_len=80)

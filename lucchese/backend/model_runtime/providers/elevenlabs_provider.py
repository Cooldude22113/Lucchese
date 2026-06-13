"""
model_runtime/providers/elevenlabs_provider.py
ElevenLabs text-to-speech provider (Rule 5).

B1 fix: the client is created lazily, not at import time. Returns None-safe state
so callers can detect "TTS not configured" (no API key) and respond with 503.
"""

from __future__ import annotations

from threading import Lock
from typing import Any

from config.integration_settings import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
from config.model_settings import ELEVENLABS_OUTPUT_FORMAT, ELEVENLABS_TTS_MODEL

_client: Any | None = None
_initialised = False
_lock = Lock()


def get_client() -> Any | None:
    """
    Return the ElevenLabs client, or None if no API key is configured.
    Created once on first call.
    """
    global _client, _initialised
    if not _initialised:
        with _lock:
            if not _initialised:
                if ELEVENLABS_API_KEY:
                    from elevenlabs.client import ElevenLabs

                    _client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
                _initialised = True
    return _client


def is_configured() -> bool:
    """True if TTS is available (an API key is set)."""
    return get_client() is not None


def synthesise(text: str) -> bytes:
    """
    Convert text to mp3 bytes for a single chunk. Raises if TTS is not configured.
    """
    client = get_client()
    if client is None:
        raise RuntimeError("ElevenLabs not configured")
    audio = client.text_to_speech.convert(
        voice_id=ELEVENLABS_VOICE_ID,
        text=text,
        model_id=ELEVENLABS_TTS_MODEL,
        output_format=ELEVENLABS_OUTPUT_FORMAT,
    )
    return b"".join(audio)

"""
audio/speech/speech_response.py
Synthesise reply text into a single mp3 byte stream (Rule 13).

Chunks are converted independently; a failure on one chunk is logged and skipped so
the rest of the reply still produces audio.
"""

from __future__ import annotations

from audio.speech.prepare_tts import prepare_tts_chunks
from model_runtime.providers import elevenlabs_provider


def synthesise_reply(text: str) -> bytes:
    """Prepare chunks from `text` and concatenate their synthesised mp3 bytes."""
    audio_bytes = b""
    for chunk in prepare_tts_chunks(text):
        try:
            audio_bytes += elevenlabs_provider.synthesise(chunk)
        except Exception as e:
            print(f"TTS chunk error: {e}")
    return audio_bytes

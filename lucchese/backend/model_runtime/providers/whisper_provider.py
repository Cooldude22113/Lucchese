"""
model_runtime/providers/whisper_provider.py
Whisper transcription model provider (Rule 5).

B1 fix: the model is loaded lazily via a module-level singleton, NOT at import
time. config.py previously called whisper.load_model("tiny") at import, which
violates Rule 21 (config must not load heavy models) and blocked startup. Any
module can now `from ... import get_whisper` cheaply; the model loads on first use.
"""

from __future__ import annotations

from threading import Lock
from typing import Any

from config.model_settings import WHISPER_MODEL

_model: Any | None = None
_lock = Lock()


def get_whisper() -> Any:
    """Return the loaded Whisper model, loading it once on first call."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                import whisper  # imported lazily so import-time stays cheap

                _model = whisper.load_model(WHISPER_MODEL)
    return _model


def transcribe(audio_path: str) -> str:
    """Transcribe an audio file path and return the stripped transcript text."""
    result = get_whisper().transcribe(audio_path)
    return result["text"].strip()

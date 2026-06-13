"""
audio/transcription/transcribe_audio.py
Transcribe an uploaded audio file to text (Rule 13).

Writes the upload to a temp file with a type-appropriate suffix, runs Whisper
(lazy-loaded provider), and returns the transcript.
"""

from __future__ import annotations

from fastapi import UploadFile

from audio.capture.temp_audio import temp_audio_file
from audio.capture.upload_normaliser import suffix_for_content_type
from model_runtime.providers.whisper_provider import transcribe as whisper_transcribe


async def transcribe_audio(file: UploadFile) -> str:
    """Read the upload, run Whisper on a temp copy, return the transcript text."""
    contents = await file.read()
    suffix = suffix_for_content_type(file.content_type)
    with temp_audio_file(contents, suffix) as tmp_path:
        return whisper_transcribe(tmp_path)

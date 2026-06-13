"""
audio/capture/upload_normaliser.py
Map an uploaded audio content-type to a temp-file suffix (Rule 13).
"""

from __future__ import annotations


def suffix_for_content_type(content_type: str | None) -> str:
    """Pick a file suffix Whisper/ffmpeg can read from the upload's content type."""
    ct = content_type or ""
    if "mp4" in ct or "m4a" in ct:
        return ".mp4"
    if "ogg" in ct:
        return ".ogg"
    if "wav" in ct:
        return ".wav"
    return ".webm"

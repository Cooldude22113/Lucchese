"""
audio/capture/temp_audio.py
Temp-file handling for uploaded audio (Rule 13).
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def temp_audio_file(contents: bytes, suffix: str) -> Iterator[str]:
    """
    Write `contents` to a temp file with `suffix`, yield its path, and delete it
    on exit (even on error).
    """
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(tmp_fd, "wb") as tmp:
            tmp.write(contents)
        yield tmp_path
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

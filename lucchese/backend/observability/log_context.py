"""
observability/log_context.py
Tee stdout to a UTF-8 file for CLI/script output (Rule 15).

Used by inspection scripts to capture terminal output to a log file while keeping
it on screen, safely on Windows cp1252 terminals.
"""

from __future__ import annotations

import io
import sys


class Tee:
    """Write to multiple streams simultaneously."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            try:
                s.write(data)
            except Exception:
                pass

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass

    def fileno(self):
        return self.streams[0].fileno()


def enable_log(path: str) -> None:
    """Redirect stdout to both the terminal and a UTF-8 log file."""
    log_file = open(path, "w", encoding="utf-8", errors="replace")
    try:
        utf8_stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )
    except AttributeError:
        utf8_stdout = sys.stdout

    sys.stdout = Tee(utf8_stdout, log_file)
    print(f"[inspect_memory] Logging to: {path}")

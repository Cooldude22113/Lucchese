"""
model_runtime/streaming/stream_parser.py
Parsing of raw provider stream lines into tokens (Rule 5).

Currently only Ollama streams token-by-token (NDJSON, one JSON object per line).
This isolates that parsing so flows do not repeat json.loads/.get plumbing.
"""

from __future__ import annotations

import json


def parse_ollama_line(line: str) -> tuple[str, bool]:
    """
    Parse one Ollama NDJSON stream line.

    Returns (token_text, done). token_text is "" when the line has no content.
    Malformed lines are treated as empty, not-done (matches prior best-effort
    behaviour that simply 'continue'd on parse failure).
    """
    try:
        chunk = json.loads(line)
    except Exception:
        return "", False
    token = chunk.get("message", {}).get("content", "") or ""
    return token, bool(chunk.get("done"))

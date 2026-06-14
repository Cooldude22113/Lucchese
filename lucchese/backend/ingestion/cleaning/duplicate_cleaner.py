"""
ingestion/cleaning/duplicate_cleaner.py
Collapse consecutive duplicate lines in imported text (Rule 8).

Some exports repeat the same line back-to-back (streaming artefacts). This drops
an exactly-repeated adjacent line while leaving intentional repetition that is
separated by other content untouched.
"""

from __future__ import annotations


def collapse_duplicates(text: str | None) -> str | None:
    """Remove a line that is identical to the immediately preceding non-blank line."""
    if not text or "\n" not in text:
        return text
    out: list[str] = []
    prev_nonblank: str | None = None
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and stripped == prev_nonblank:
            continue
        out.append(line)
        if stripped:
            prev_nonblank = stripped
    return "\n".join(out)

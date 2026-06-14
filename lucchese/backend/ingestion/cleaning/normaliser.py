"""
ingestion/cleaning/normaliser.py
Unicode/whitespace normalisation for imported text (Rule 8).

Applies NFC normalisation, repairs the common mojibake seen in these exports
(e.g. the `�`-style replacement characters wrapping smart quotes in Grok
render_searched_image text and ChatGPT tether_quote text), straightens smart
quotes, and trims trailing whitespace.
"""

from __future__ import annotations

import re
import unicodedata

# Mojibake fixups observed in the raw data. The replacement char (U+FFFD) appears
# around words where smart quotes were lost in an earlier round-trip; collapse the
# obvious paired cases and strip stragglers.
_SMART_QUOTES = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...",
}

_MOJIBAKE_PAIR_RE = re.compile(r"�([^�]{0,40}?)�")
_TRAILING_WS_RE = re.compile(r"[ \t]+(\n|$)")


def normalise(text: str | None) -> str | None:
    """Normalise unicode, repair mojibake, straighten quotes, trim trailing space."""
    if not text:
        return text
    text = unicodedata.normalize("NFC", text)
    # `�word�` → `"word"` (most common paired case), then drop any leftover U+FFFD.
    text = _MOJIBAKE_PAIR_RE.sub(r'"\1"', text)
    text = text.replace("�", "")
    for bad, good in _SMART_QUOTES.items():
        text = text.replace(bad, good)
    text = _TRAILING_WS_RE.sub(r"\1", text)
    return text

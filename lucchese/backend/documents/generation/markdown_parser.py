"""
documents/generation/markdown_parser.py
Lightweight markdown line classification for docx generation (Rule 12).
"""

from __future__ import annotations

import re


def looks_like_section_header(line: str) -> bool:
    """
    Detect plain-text section headers like "Property Basics:" when the model didn't
    use markdown heading syntax. Rules: ends with colon, 1-5 words, no sentence
    punctuation, starts with a capital.
    """
    s = line.strip()
    if not s.endswith(":"):
        return False
    if len(s) > 50:
        return False
    if not s[0].isupper():
        return False
    word_count = len(s.rstrip(":").split())
    if word_count > 5:
        return False
    if re.search(r"[,\.!?']", s.rstrip(":")):
        return False
    return True

"""
documents/generation/inline_formatting.py
Inline **bold** / *italic* markdown rendering within a docx paragraph (Rule 12).
"""

from __future__ import annotations

import re

_INLINE_PATTERN = re.compile(r"(\*\*.*?\*\*|\*.*?\*)")


def add_inline_formatting(para, text: str) -> None:
    """Add `text` to a python-docx paragraph, honouring **bold** and *italic*."""
    for part in _INLINE_PATTERN.split(text):
        if part.startswith("**") and part.endswith("**"):
            run = para.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("*") and part.endswith("*"):
            run = para.add_run(part[1:-1])
            run.italic = True
        else:
            para.add_run(part)

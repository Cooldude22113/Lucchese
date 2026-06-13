"""
memory/commands/detect_memory_command.py
Detect explicit remember/forget commands in a message (Rule 7).
"""

from __future__ import annotations

import re

REMEMBER_PATTERNS = [
    r"\bremember that\b(.+)",
    r"\bremember:\b(.+)",
    r"\bsave this\b(.+)",
    r"\bstore this\b(.+)",
    r"\bnote that\b(.+)",
]

FORGET_PATTERNS = [
    r"\bforget that\b(.+)",
    r"\bforget\b (.+)",
    r"\bdelete that\b",
    r"\bunremember\b(.+)",
    r"\bremove that\b",
]


def detect_memory_command(message: str) -> tuple[str | None, str | None]:
    """Return ('remember', text), ('forget', text), or (None, None)."""
    msg = message.lower().strip()

    for pattern in REMEMBER_PATTERNS:
        match = re.search(pattern, msg)
        if match:
            return ("remember", match.group(1).strip())

    for pattern in FORGET_PATTERNS:
        match = re.search(pattern, msg)
        if match:
            content = match.group(1).strip() if match.lastindex else ""
            return ("forget", content)

    return (None, None)

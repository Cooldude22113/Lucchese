"""
business_logic/roleplay/roleplay_detection.py
Phrase detection for starting and ending a roleplay (Rule 10).
"""

from __future__ import annotations

START_PHRASES = [
    "practice pitch", "role play property", "roleplay property", "start practice",
]

END_PHRASES = [
    "end practice", "end role play", "end roleplay", "stop practice",
]


def is_start_phrase(message: str) -> bool:
    """True if the message asks to start a property-pitch roleplay."""
    msg = message.lower().strip()
    return any(p in msg for p in START_PHRASES)


def is_end_phrase(message: str) -> bool:
    """True if the message asks to end the current roleplay."""
    msg = message.lower().strip()
    return any(p in msg for p in END_PHRASES)

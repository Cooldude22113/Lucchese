"""
web/search/search_decision.py
Decide whether a chat message warrants a web search (Rule 14).
"""

from __future__ import annotations

import re

WEB_TRIGGERS = [
    r"\b(latest|recent|current news|today|tonight)\b",
    r"\b(news|weather|score|results?|standings?)\b",
    r"\b(search|look up|google)\b",
    r"\b(released?|launched?|announced?)\b",
    r"\b(final|winner|champion|trophy)\b",
]

# Topics that should stay internal (memory/menu/etc.) and never trigger web search.
_INTERNAL_SIGNALS = [
    "macro", "recipe", "ingredient", "meal", "my ", "i am", "i'm",
    "analyse deal", "analyze deal", "practice pitch", "remember",
    "what have i", "what did i", "shopify",
]


def needs_web_search(message: str) -> bool:
    """True if the message looks like it needs fresh web information."""
    msg = message.lower()

    if re.search(r"https?://|www\.|\.co\.uk|\.com|\.io", msg):
        return True

    if any(s in msg for s in _INTERNAL_SIGNALS):
        return False

    return any(re.search(p, msg) for p in WEB_TRIGGERS)

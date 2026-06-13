"""
application/commands/business_commands.py
Detect business-domain chat commands (Rule 4 boundary for the chat flow).
"""

from __future__ import annotations

import re

_SHOPIFY_PATTERN = re.compile(r"shopify add (.+)|add (.+) to shopify")


def detect_shopify_meal(message: str) -> str | None:
    """Return the meal name if the message is a 'shopify add <meal>' command."""
    match = _SHOPIFY_PATTERN.search(message.lower())
    if not match:
        return None
    return (match.group(1) or match.group(2)).strip()


def is_deal_command(message: str) -> bool:
    """True if the message starts a deal analysis."""
    return message.lower().startswith(("analyse deal:", "analyze deal:"))

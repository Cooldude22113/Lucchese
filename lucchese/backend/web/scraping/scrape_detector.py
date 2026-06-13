"""
web/scraping/scrape_detector.py
Detect a "scrape <url>" command in a chat message (Rule 14).
"""

from __future__ import annotations

import re

SCRAPE_PATTERN = re.compile(r"\bscrape\s+(https?://\S+|\S+\.\S+)", re.IGNORECASE)


def detect_scrape_command(message: str) -> str | None:
    """Return the URL if the message is a scrape command, else None."""
    match = SCRAPE_PATTERN.search(message)
    return match.group(1).strip() if match else None

"""
application/commands/scrape_commands.py
Scrape command detection surface for the chat flow (Rule 4).

Thin re-export of the web-scraping detector so the chat flow depends on a stable
command boundary rather than reaching into web/ directly.
"""

from __future__ import annotations

from web.scraping.scrape_detector import detect_scrape_command

__all__ = ["detect_scrape_command"]

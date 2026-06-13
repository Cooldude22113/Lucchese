"""
web/search/ddgs_search.py
DuckDuckGo web search (Rule 14).

Runs the blocking DDGS client off the event loop and formats results. Returns ""
on any failure so chat never breaks on a search error.
"""

from __future__ import annotations

import asyncio

from web.search.result_formatter import format_web_results


async def do_web_search(query: str, max_results: int = 4) -> str:
    """Search the web for `query`; returns a formatted block or "" on failure."""
    try:
        from ddgs import DDGS

        results = await asyncio.to_thread(
            lambda: list(DDGS().text(query, max_results=max_results))
        )
        return format_web_results(results)
    except Exception:
        return ""

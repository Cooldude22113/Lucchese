"""
web/search/result_formatter.py
Format raw DDGS results into a prompt-ready block (Rule 14).
"""

from __future__ import annotations


def format_web_results(results: list[dict]) -> str:
    """Render search results as a bulleted block, or "" if empty."""
    if not results:
        return ""
    lines = ["[Web search results:]"]
    for r in results:
        lines.append(f"• {r.get('title', '')}: {r.get('body', '')} ({r.get('href', '')})")
    return "\n".join(lines)

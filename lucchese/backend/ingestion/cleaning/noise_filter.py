"""
ingestion/cleaning/noise_filter.py
Strip structural noise from imported display text (Rule 8).

The parsers already lift behavioural cards out into their own rows; this is a
belt-and-braces pass that removes any leftover <grok:render>/<xai:*> tags and
collapses runs of blank lines so the stored display text reads cleanly.
"""

from __future__ import annotations

import re

_RENDER_RE = re.compile(r"<grok:render\b[^>]*>.*?</grok:render>", re.DOTALL)
_XAI_RE = re.compile(r"<xai:[^>]*>.*?</xai:[^>]*>", re.DOTALL)
_TAG_LEFTOVER_RE = re.compile(r"</?xai:[^>]*>|</?grok:[^>]*>")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def strip_noise(text: str | None) -> str | None:
    """Remove leftover render/xai tags and collapse 3+ blank lines to one."""
    if not text:
        return text
    text = _RENDER_RE.sub("", text)
    text = _XAI_RE.sub("", text)
    text = _TAG_LEFTOVER_RE.sub("", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text

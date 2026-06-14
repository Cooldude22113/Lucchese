"""
ingestion/parsing/grok_tags.py
Parse and strip Grok's inline XML-ish cards (Rule 8: isolate format quirks).

Grok embeds machine cards inside reasoning traces and message text:
  - <xai:tool_usage_card> … <xai:tool_name>web_search</xai:tool_name>
    <xai:tool_args><![CDATA[{"query":…,"num_results":…}]]></xai:tool_args> …
      → tool calls / web searches
  - <grok:render … type="render_inline_citation"> … </grok:render>  → citation markers
  - <grok:render … type="render_searched_image"> … </grok:render>   → image markers

This module turns those cards into behavioural records and strips them out of the
display text. The raw text (with cards intact) is kept separately for fidelity.
"""

from __future__ import annotations

import json
import re

from ingestion.parsing.normalized_models import (
    ParsedAttachment,
    ParsedSearchResult,
    ParsedToolCall,
    ParsedWebSearch,
)

_TOOL_CARD_RE = re.compile(r"<xai:tool_usage_card>(.*?)</xai:tool_usage_card>", re.DOTALL)
_TOOL_NAME_RE = re.compile(r"<xai:tool_name>(.*?)</xai:tool_name>", re.DOTALL)
_TOOL_ARGS_RE = re.compile(
    r"<xai:tool_args>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</xai:tool_args>", re.DOTALL
)
_RENDER_RE = re.compile(r"<grok:render\b[^>]*>.*?</grok:render>", re.DOTALL)
_RENDER_TYPE_RE = re.compile(r'type="([^"]+)"')
_ARG_RE = re.compile(r'<argument name="([^"]+)">(.*?)</argument>', re.DOTALL)
_XAI_ANY_RE = re.compile(r"<xai:[^>]*>.*?</xai:[^>]*>", re.DOTALL)
_TAG_LEFTOVER_RE = re.compile(r"</?xai:[^>]*>|</?grok:[^>]*>")


def parse_tool_cards(text: str | None, created_at: str | None = None) -> dict:
    """
    Extract <xai:tool_usage_card> cards from a reasoning trace / message.

    Returns {tool_calls, web_searches}: a web_search card (tool_name == web_search)
    becomes a ParsedWebSearch with query/num_results; any other tool card becomes a
    ParsedToolCall.
    """
    tool_calls: list[ParsedToolCall] = []
    web_searches: list[ParsedWebSearch] = []
    if not text:
        return {"tool_calls": tool_calls, "web_searches": web_searches}

    for card in _TOOL_CARD_RE.findall(text):
        name_m = _TOOL_NAME_RE.search(card)
        tool_name = name_m.group(1).strip() if name_m else None
        args = _parse_args(card)

        if tool_name == "web_search":
            web_searches.append(
                ParsedWebSearch(
                    query=_as_str(args.get("query")),
                    num_results=_as_int(args.get("num_results")),
                    search_source="grok",
                    created_at=created_at,
                )
            )
        else:
            tool_calls.append(
                ParsedToolCall(
                    tool_name=tool_name,
                    arguments=args or None,
                    created_at=created_at,
                )
            )
    return {"tool_calls": tool_calls, "web_searches": web_searches}


def parse_render_cards(text: str | None, created_at: str | None = None) -> dict:
    """
    Extract <grok:render> cards from message text.

    citation_card / render_inline_citation → ParsedSearchResult(kind='citation')
    image_card / render_searched_image     → ParsedAttachment(kind='image_asset_pointer')
    """
    search_results: list[ParsedSearchResult] = []
    attachments: list[ParsedAttachment] = []
    if not text:
        return {"search_results": search_results, "attachments": attachments}

    for card in _RENDER_RE.findall(text):
        type_m = _RENDER_TYPE_RE.search(card)
        rtype = type_m.group(1) if type_m else ""
        args = {name: _strip_quotes(val) for name, val in _ARG_RE.findall(card)}

        if rtype == "render_inline_citation":
            search_results.append(
                ParsedSearchResult(
                    kind="citation",
                    title=args.get("citation_id"),
                    created_at=created_at,
                )
            )
        elif rtype == "render_searched_image":
            attachments.append(
                ParsedAttachment(
                    kind="image_asset_pointer",
                    source_asset_id=args.get("image_id"),
                    created_at=created_at,
                )
            )
    return {"search_results": search_results, "attachments": attachments}


def strip_cards(text: str | None) -> str | None:
    """Remove all xai/grok cards (and leftover tags) from display text."""
    if not text:
        return text
    text = _RENDER_RE.sub("", text)
    text = _XAI_ANY_RE.sub("", text)
    text = _TAG_LEFTOVER_RE.sub("", text)
    return text


# ── helpers ───────────────────────────────────────────────────────────────────
def _parse_args(card: str) -> dict:
    m = _TOOL_ARGS_RE.search(card)
    if not m:
        return {}
    raw = m.group(1).strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except (ValueError, TypeError):
        return {"raw": raw}


def _strip_quotes(value: str) -> str:
    return value.strip().strip('"')


def _as_str(value):
    return str(value) if value is not None else None


def _as_int(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None

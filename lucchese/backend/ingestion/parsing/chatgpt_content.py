"""
ingestion/parsing/chatgpt_content.py
Interpret a single ChatGPT message's content + metadata (Rule 8: isolate format
quirks).

Given one raw `message` dict (the `message` value of a mapping node), this module
produces the display text and the behavioural records (tool calls, web searches,
search results, attachments) that explain the message. The tree walking lives in
chatgpt_parser; the per-message interpretation lives here.
"""

from __future__ import annotations

from ingestion.parsing.metadata_parser import domain_of, epoch_to_iso
from ingestion.parsing.normalized_models import (
    ParsedAttachment,
    ParsedSearchResult,
    ParsedToolCall,
    ParsedWebSearch,
)

# Roles that ChatGPT routes through a tool author.
_TOOL_AUTHORS = {"python", "web", "myfiles_browser", "bio", "dalle.text2im"}


def extract_text(content: dict) -> str | None:
    """Flatten any ChatGPT content_type into display text (image parts dropped)."""
    if not isinstance(content, dict):
        return None
    ctype = content.get("content_type")

    if ctype in ("text", "reasoning_recap", "thoughts"):
        parts = content.get("parts")
        if parts:
            return "\n".join(p for p in parts if isinstance(p, str))
        return content.get("text")

    if ctype == "multimodal_text":
        chunks = [p for p in content.get("parts", []) if isinstance(p, str)]
        return "\n".join(chunks) if chunks else None

    if ctype in ("code", "execution_output", "system_error", "tether_browsing_display"):
        return content.get("text")

    if ctype == "tether_quote":
        return content.get("text")

    if ctype == "user_editable_context":
        # Profile/context blobs: keep whatever text-ish fields exist.
        return content.get("text") or content.get("user_instructions")

    # Unknown shape: fall back to a text field if present.
    return content.get("text")


def extract_behaviour(message: dict) -> dict:
    """
    Pull behavioural records out of one ChatGPT message.

    Returns a dict with keys tool_calls / web_searches / search_results /
    attachments, each a list of the corresponding Parsed* dataclass.
    """
    content = message.get("content", {}) or {}
    metadata = message.get("metadata", {}) or {}
    author = message.get("author", {}) or {}
    created_at = _msg_time(message)

    tool_calls: list[ParsedToolCall] = []
    web_searches: list[ParsedWebSearch] = []
    search_results: list[ParsedSearchResult] = []
    attachments: list[ParsedAttachment] = []

    _collect_tool_calls(author, message, content, metadata, created_at, tool_calls)
    _collect_web_searches(metadata, created_at, web_searches)
    _collect_search_results(content, metadata, created_at, search_results)
    _collect_attachments(content, metadata, created_at, attachments)

    return {
        "tool_calls": tool_calls,
        "web_searches": web_searches,
        "search_results": search_results,
        "attachments": attachments,
    }


# ── tool calls ────────────────────────────────────────────────────────────────
def _collect_tool_calls(author, message, content, metadata, created_at, out):
    name = author.get("name")
    recipient = message.get("recipient")
    command = metadata.get("command")
    is_tool = author.get("role") == "tool"
    routed = recipient not in (None, "all")

    if not (name or command or is_tool or routed):
        return

    arguments: dict = {}
    if content.get("content_type") == "code" and content.get("text"):
        arguments["code"] = content["text"]
    if metadata.get("args") is not None:
        arguments["args"] = metadata["args"]

    out.append(
        ParsedToolCall(
            tool_name=name or recipient,
            command=command,
            arguments=arguments or None,
            created_at=created_at,
        )
    )


# ── web searches ──────────────────────────────────────────────────────────────
def _collect_web_searches(metadata, created_at, out):
    groups = metadata.get("search_result_groups")
    if not groups:
        return
    total = sum(len(g.get("entries", []) or []) for g in groups if isinstance(g, dict))
    out.append(
        ParsedWebSearch(
            query=None,  # ChatGPT does not store the literal query alongside the groups
            num_results=total or None,
            search_source=metadata.get("search_source")
            or metadata.get("client_reported_search_source"),
            created_at=created_at,
        )
    )


# ── search results ────────────────────────────────────────────────────────────
def _collect_search_results(content, metadata, created_at, out):
    rank = 0
    # search_result_groups[].entries[]
    for group in metadata.get("search_result_groups", []) or []:
        for entry in group.get("entries", []) or []:
            if not isinstance(entry, dict):
                continue
            url = entry.get("url")
            out.append(
                ParsedSearchResult(
                    kind="search_result",
                    url=url,
                    domain=entry.get("domain") or domain_of(url),
                    title=entry.get("title"),
                    snippet=entry.get("snippet"),
                    pub_date=epoch_to_iso(entry.get("pub_date")),
                    rank=rank,
                    created_at=created_at,
                )
            )
            rank += 1

    # content_references[].items[] (richer citations)
    for ref in metadata.get("content_references", []) or []:
        for item in (ref.get("items") or []) if isinstance(ref, dict) else []:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            url = item.get("url")
            out.append(
                ParsedSearchResult(
                    kind="citation",
                    url=url,
                    domain=item.get("attribution") or domain_of(url),
                    title=item.get("title"),
                    snippet=item.get("snippet"),
                    pub_date=epoch_to_iso(item.get("pub_date")),
                    created_at=created_at,
                )
            )

    # tether_quote content block
    if content.get("content_type") == "tether_quote":
        out.append(
            ParsedSearchResult(
                kind="tether_quote",
                url=content.get("url"),
                domain=content.get("domain") or domain_of(content.get("url")),
                title=content.get("title"),
                snippet=content.get("text"),
                created_at=created_at,
            )
        )

    # safe_urls
    for url in metadata.get("safe_urls", []) or []:
        if not isinstance(url, str):
            continue
        out.append(
            ParsedSearchResult(
                kind="safe_url",
                url=url,
                domain=domain_of(url),
                created_at=created_at,
            )
        )


# ── attachments ───────────────────────────────────────────────────────────────
def _collect_attachments(content, metadata, created_at, out):
    for att in metadata.get("attachments", []) or []:
        if not isinstance(att, dict):
            continue
        out.append(
            ParsedAttachment(
                kind="file",
                source_asset_id=att.get("id"),
                name=att.get("name"),
                mime_type=att.get("mime_type"),
                size=att.get("size"),
                width=att.get("width"),
                height=att.get("height"),
                created_at=created_at,
            )
        )

    if content.get("content_type") == "multimodal_text":
        for part in content.get("parts", []) or []:
            if not isinstance(part, dict):
                continue
            if part.get("content_type") == "image_asset_pointer":
                out.append(
                    ParsedAttachment(
                        kind="image_asset_pointer",
                        source_asset_id=part.get("asset_pointer"),
                        mime_type=None,
                        size=part.get("size_bytes"),
                        width=part.get("width"),
                        height=part.get("height"),
                        created_at=created_at,
                    )
                )


def _msg_time(message: dict) -> str | None:
    return epoch_to_iso(message.get("create_time"))

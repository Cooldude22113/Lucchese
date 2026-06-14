"""
ingestion/parsing/grok_parser.py
Grok export → ParsedConversation (Rule 8: raw → normalized).

Each item is `{conversation, responses}`. Every `responses[].response` becomes a
ParsedMessage, threaded via `parent_response_id`; the `leaf_response_id` chain marks
on_active_path. `sender` casing is normalised (human→user, ASSISTANT/assistant→
assistant). Behavioural records come from the response's own arrays plus the
xai/grok cards parsed by grok_tags.
"""

from __future__ import annotations

from ingestion.parsing.grok_tags import (
    parse_render_cards,
    parse_tool_cards,
    strip_cards,
)
from ingestion.parsing.metadata_parser import domain_of, mongo_date_to_iso
from ingestion.parsing.normalized_models import (
    ParsedAttachment,
    ParsedConversation,
    ParsedMessage,
    ParsedReasoningTrace,
    ParsedSearchResult,
)

_PROMOTED_CONV_KEYS = {
    "id", "title", "summary", "create_time", "modify_time",
    "system_prompt_name", "starred", "leaf_response_id",
}


def parse_conversation(item: dict) -> ParsedConversation:
    """Normalise one raw Grok `{conversation, responses}` item."""
    conv = item.get("conversation", {}) or {}
    responses = item.get("responses", []) or []
    source_id = str(conv.get("id", ""))
    active_ids = _active_path_ids(responses, conv.get("leaf_response_id"))

    messages: list[ParsedMessage] = []
    for seq, r in enumerate(responses):
        resp = r.get("response", {}) or {}
        parsed = _parse_response(resp, source_id)
        parsed.sequence = seq
        parsed.on_active_path = resp.get("_id") in active_ids
        messages.append(parsed)

    return ParsedConversation(
        source="grok",
        source_conversation_id=source_id,
        title=conv.get("title"),
        summary=conv.get("summary"),
        created_at=mongo_date_to_iso(conv.get("create_time")),
        updated_at=mongo_date_to_iso(conv.get("modify_time")),
        default_model=None,
        system_prompt_name=conv.get("system_prompt_name"),
        starred=bool(conv.get("starred")),
        archived=False,
        source_metadata={k: v for k, v in conv.items() if k not in _PROMOTED_CONV_KEYS},
        messages=messages,
    )


def _parse_response(resp: dict, source_id: str) -> ParsedMessage:
    created_at = mongo_date_to_iso(resp.get("create_time"))
    raw_text = resp.get("message")
    role = _normalise_sender(resp.get("sender"))

    pm = ParsedMessage(
        source_message_id=str(resp.get("_id", "")),
        source_parent_id=_as_opt_str(resp.get("parent_response_id")),
        role=role,
        author_name=None,
        content_type="text",
        text=strip_cards(raw_text),         # display text (further cleaned by pipeline)
        raw_text=raw_text,
        model=resp.get("model"),
        recipient=None,
        status="partial" if resp.get("partial") else None,
        end_turn=None,
        weight=None,
        created_at=created_at,
        updated_at=None,
        source_metadata=resp.get("metadata") or {},
    )

    _collect_behaviour(resp, created_at, pm)
    return pm


def _collect_behaviour(resp: dict, created_at: str | None, pm: ParsedMessage) -> None:
    # Cards embedded in the visible message (citations / images).
    msg_cards = parse_render_cards(resp.get("message"), created_at)
    pm.search_results.extend(msg_cards["search_results"])
    pm.attachments.extend(msg_cards["attachments"])

    # Reasoning traces: thinking_trace + agent_thinking_traces + steps; tool cards
    # inside them yield web_searches / tool_calls.
    seq = 0
    trace = resp.get("thinking_trace")
    if trace:
        pm.reasoning_traces.append(
            ParsedReasoningTrace(
                kind="thinking_trace",
                content=trace,
                started_at=mongo_date_to_iso(resp.get("thinking_start_time")),
                ended_at=mongo_date_to_iso(resp.get("thinking_end_time")),
                seq=seq,
            )
        )
        seq += 1
        _absorb_tool_cards(trace, created_at, pm)

    for att in resp.get("agent_thinking_traces", []) or []:
        content = att.get("thinking_trace") if isinstance(att, dict) else None
        if not content:
            continue
        pm.reasoning_traces.append(
            ParsedReasoningTrace(kind="agent_thinking_trace", content=content, seq=seq)
        )
        seq += 1
        _absorb_tool_cards(content, created_at, pm)

    for step in resp.get("steps", []) or []:
        tagged = step.get("tagged_text", {}) if isinstance(step, dict) else {}
        card_text = tagged.get("tool_usage_card") if isinstance(tagged, dict) else None
        summary = tagged.get("summary") if isinstance(tagged, dict) else None
        if summary or card_text:
            pm.reasoning_traces.append(
                ParsedReasoningTrace(kind="step", content=summary or card_text, seq=seq)
            )
            seq += 1
        if card_text:
            _absorb_tool_cards(card_text, created_at, pm)

    # web_search_results[] — the actual fetched results.
    rank = 0
    for sr in resp.get("web_search_results", []) or []:
        if not isinstance(sr, dict):
            continue
        url = sr.get("url")
        pm.search_results.append(
            ParsedSearchResult(
                kind="search_result",
                url=url,
                domain=sr.get("site_name") or domain_of(url),
                title=sr.get("title"),
                snippet=sr.get("preview") or sr.get("description"),
                rank=rank,
                created_at=created_at,
            )
        )
        rank += 1

    # xpost_ids[] → search_results(kind='xpost')
    for xid in resp.get("xpost_ids", []) or []:
        pm.search_results.append(
            ParsedSearchResult(kind="xpost", url=None, title=str(xid), created_at=created_at)
        )

    # file_attachments[] (asset id strings) + generated_image_urls[].
    for asset_id in resp.get("file_attachments", []) or []:
        pm.attachments.append(
            ParsedAttachment(kind="file", source_asset_id=str(asset_id), created_at=created_at)
        )
    for url in resp.get("generated_image_urls", []) or []:
        pm.attachments.append(
            ParsedAttachment(kind="generated_image", url=str(url), created_at=created_at)
        )


def _absorb_tool_cards(text: str, created_at: str | None, pm: ParsedMessage) -> None:
    cards = parse_tool_cards(text, created_at)
    pm.tool_calls.extend(cards["tool_calls"])
    pm.web_searches.extend(cards["web_searches"])


def _normalise_sender(sender: str | None) -> str:
    s = (sender or "").lower()
    if s == "human":
        return "user"
    if s in ("assistant", "ai", "bot"):
        return "assistant"
    return s or "unknown"


def _active_path_ids(responses: list, leaf_id: str | None) -> set[str]:
    """Walk leaf_response_id → root via parent_response_id."""
    by_id = {
        r.get("response", {}).get("_id"): r.get("response", {})
        for r in responses
        if isinstance(r, dict)
    }
    ids: set[str] = set()
    node_id = leaf_id
    seen: set[str] = set()
    while node_id and node_id in by_id and node_id not in seen:
        seen.add(node_id)
        ids.add(node_id)
        node_id = by_id[node_id].get("parent_response_id")
    return ids


def _as_opt_str(value):
    return str(value) if value is not None else None

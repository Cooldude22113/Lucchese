"""
ingestion/parsing/chatgpt_parser.py
ChatGPT export → ParsedConversation (Rule 8: raw → normalized).

Walks a conversation's `mapping` tree, emits every node that carries a `message`
as a ParsedMessage (full fidelity: tool/system/hidden nodes and regenerations are
all kept), threads them via the node `parent`, and flags the messages on the
`current_node`→root path with on_active_path. Per-message text and behavioural
records come from chatgpt_content.
"""

from __future__ import annotations

from ingestion.parsing.chatgpt_content import extract_behaviour, extract_text
from ingestion.parsing.metadata_parser import epoch_to_iso, first
from ingestion.parsing.normalized_models import ParsedConversation, ParsedMessage

# Conversation keys promoted to first-class columns; everything else → source_metadata.
_PROMOTED_CONV_KEYS = {
    "id", "conversation_id", "title", "create_time", "update_time",
    "default_model_slug", "is_starred", "is_archived", "mapping", "current_node",
}


def parse_conversation(raw: dict) -> ParsedConversation:
    """Normalise one raw ChatGPT conversation dict."""
    source_id = str(first(raw, "conversation_id", "id", default=""))
    mapping = raw.get("mapping", {}) or {}
    active_ids = _active_path_ids(mapping, raw.get("current_node"))

    messages: list[ParsedMessage] = []
    sequence = 0
    for node_id, node in mapping.items():
        msg = node.get("message")
        if not msg:
            continue
        parsed = _parse_node(node_id, node, msg, source_id)
        parsed.on_active_path = node_id in active_ids
        parsed.sequence = sequence
        sequence += 1
        messages.append(parsed)

    return ParsedConversation(
        source="chatgpt",
        source_conversation_id=source_id,
        title=raw.get("title"),
        summary=None,
        created_at=epoch_to_iso(raw.get("create_time")),
        updated_at=epoch_to_iso(raw.get("update_time")),
        default_model=raw.get("default_model_slug"),
        system_prompt_name=None,
        starred=bool(raw.get("is_starred")),
        archived=bool(raw.get("is_archived")),
        source_metadata={k: v for k, v in raw.items() if k not in _PROMOTED_CONV_KEYS},
        messages=messages,
    )


def _parse_node(node_id: str, node: dict, msg: dict, source_id: str) -> ParsedMessage:
    author = msg.get("author", {}) or {}
    content = msg.get("content", {}) or {}
    metadata = msg.get("metadata", {}) or {}
    raw_text = extract_text(content)
    behaviour = extract_behaviour(msg)

    pm = ParsedMessage(
        source_message_id=node_id,
        source_parent_id=node.get("parent"),
        role=author.get("role") or "unknown",
        author_name=author.get("name"),
        content_type=content.get("content_type"),
        text=raw_text,                     # cleaned later by the pipeline
        raw_text=raw_text,
        model=metadata.get("model_slug"),
        recipient=msg.get("recipient"),
        status=msg.get("status"),
        end_turn=msg.get("end_turn"),
        weight=msg.get("weight"),
        is_hidden=bool(metadata.get("is_visually_hidden_from_conversation")),
        created_at=epoch_to_iso(msg.get("create_time")),
        updated_at=epoch_to_iso(msg.get("update_time")),
        source_metadata=metadata,
        tool_calls=behaviour["tool_calls"],
        web_searches=behaviour["web_searches"],
        search_results=behaviour["search_results"],
        attachments=behaviour["attachments"],
    )
    return pm


def _active_path_ids(mapping: dict, current_node: str | None) -> set[str]:
    """Walk current_node → root via `parent`, returning the kept-thread node ids."""
    ids: set[str] = set()
    node_id = current_node
    seen: set[str] = set()
    while node_id and node_id in mapping and node_id not in seen:
        seen.add(node_id)
        ids.add(node_id)
        node_id = mapping[node_id].get("parent")
    return ids

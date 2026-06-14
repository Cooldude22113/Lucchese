"""
ingestion/pipelines/conversation_pipeline.py
Persist one ParsedConversation into the canonical store (Rule 8 + Rule 3).

Steps for a single conversation, all inside one transaction so a failure rolls
back cleanly:
  1. clean each message's display text (raw_text kept untouched for fidelity)
  2. insert the conversation row → integer id; record id_map
  3. insert each message WITHOUT parent_id → integer id; record id_map; insert its
     behavioural rows (tool_calls, web_searches, search_results, attachments,
     reasoning_traces)
  4. resolve every message's parent_id from id_map (the "paired by old id" step)
  5. cache message_count

Storage stays decoupled (Rule 21): this maps dataclasses to plain repo call args;
the repositories never import ingestion.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from config.paths import CONVERSATION_STORE_DB
from ingestion.cleaning.text_cleaner import clean_text
from ingestion.parsing.normalized_models import ParsedConversation, ParsedMessage
from ingestion.status.import_job import SourceTally
from storage.sqlite.connection import session
from storage.sqlite.repositories.conversation_store import (
    attachments as attachments_repo,
    conversations as conversations_repo,
    id_map as id_map_repo,
    messages as messages_repo,
    reasoning_traces as reasoning_repo,
    search_results as search_results_repo,
    tool_calls as tool_calls_repo,
    web_searches as web_searches_repo,
)


def persist_conversation(parsed: ParsedConversation, tally: SourceTally) -> None:
    """Persist a conversation and all its rows; update the running tally."""
    source = parsed.source
    with session(CONVERSATION_STORE_DB) as con:
        conv_id = conversations_repo.insert(con, _conversation_row(parsed))
        id_map_repo.record(con, source, "conversation", parsed.source_conversation_id, conv_id)

        for msg in parsed.messages:
            new_msg_id = messages_repo.insert(con, _message_row(conv_id, msg))
            id_map_repo.record(con, source, "message", msg.source_message_id, new_msg_id)
            _persist_behaviour(con, source, conv_id, new_msg_id, msg, tally)
            tally.messages_imported += 1

        _resolve_parents(con, source, conv_id, parsed.messages)
        conversations_repo.update_message_count(con, conv_id, len(parsed.messages))

    tally.conversations_imported += 1
    if not parsed.messages:
        tally.conversations_empty += 1


def count_only(parsed: ParsedConversation, tally: SourceTally) -> None:
    """Dry-run path: tally what WOULD be written, without touching the DB."""
    tally.conversations_imported += 1
    if not parsed.messages:
        tally.conversations_empty += 1
    for msg in parsed.messages:
        tally.messages_imported += 1
        tally.tool_calls += len(msg.tool_calls)
        tally.web_searches += len(msg.web_searches)
        tally.search_results += len(msg.search_results) + sum(
            len(ws.results) for ws in msg.web_searches
        )
        tally.attachments += len(msg.attachments)
        tally.reasoning_traces += len(msg.reasoning_traces)


# ── row builders ──────────────────────────────────────────────────────────────
def _conversation_row(parsed: ParsedConversation) -> dict:
    return {
        "source": parsed.source,
        "source_conversation_id": parsed.source_conversation_id,
        "title": parsed.title,
        "summary": parsed.summary,
        "created_at": parsed.created_at,
        "updated_at": parsed.updated_at,
        "default_model": parsed.default_model,
        "system_prompt_name": parsed.system_prompt_name,
        "starred": parsed.starred,
        "archived": parsed.archived,
        "message_count": len(parsed.messages),
        "source_metadata": _json(parsed.source_metadata),
    }


def _message_row(conv_id: int, msg: ParsedMessage) -> dict:
    return {
        "conversation_id": conv_id,
        "source_message_id": msg.source_message_id,
        "parent_id": None,                     # resolved after all inserts
        "role": msg.role,
        "author_name": msg.author_name,
        "content_type": msg.content_type,
        "text": clean_text(msg.text),
        "raw_text": msg.raw_text,
        "model": msg.model,
        "recipient": msg.recipient,
        "status": msg.status,
        "end_turn": msg.end_turn,
        "weight": msg.weight,
        "sequence": msg.sequence,
        "on_active_path": msg.on_active_path,
        "is_hidden": msg.is_hidden,
        "created_at": msg.created_at,
        "updated_at": msg.updated_at,
        "source_metadata": _json(msg.source_metadata),
    }


def _persist_behaviour(con, source, conv_id, msg_id, msg, tally: SourceTally) -> None:
    for tc in msg.tool_calls:
        tool_calls_repo.insert(con, {
            "conversation_id": conv_id, "message_id": msg_id, "source": source,
            "tool_name": tc.tool_name, "command": tc.command,
            "arguments": _json(tc.arguments), "created_at": tc.created_at,
        })
        tally.tool_calls += 1

    for ws in msg.web_searches:
        ws_id = web_searches_repo.insert(con, {
            "conversation_id": conv_id, "message_id": msg_id, "source": source,
            "query": ws.query, "num_results": ws.num_results,
            "search_source": ws.search_source, "created_at": ws.created_at,
        })
        tally.web_searches += 1
        for sr in ws.results:
            _insert_search_result(con, source, conv_id, msg_id, sr, ws_id)
            tally.search_results += 1

    for sr in msg.search_results:
        _insert_search_result(con, source, conv_id, msg_id, sr, None)
        tally.search_results += 1

    for att in msg.attachments:
        attachments_repo.insert(con, {
            "conversation_id": conv_id, "message_id": msg_id, "source": source,
            "kind": att.kind, "source_asset_id": att.source_asset_id, "name": att.name,
            "mime_type": att.mime_type, "url": att.url, "size": att.size,
            "width": att.width, "height": att.height, "created_at": att.created_at,
        })
        tally.attachments += 1

    for rt in msg.reasoning_traces:
        reasoning_repo.insert(con, {
            "conversation_id": conv_id, "message_id": msg_id, "source": source,
            "kind": rt.kind, "content": rt.content,
            "started_at": rt.started_at, "ended_at": rt.ended_at, "seq": rt.seq,
        })
        tally.reasoning_traces += 1


def _insert_search_result(con, source, conv_id, msg_id, sr, web_search_id) -> None:
    search_results_repo.insert(con, {
        "conversation_id": conv_id, "message_id": msg_id, "web_search_id": web_search_id,
        "source": source, "kind": sr.kind, "url": sr.url, "domain": sr.domain,
        "title": sr.title, "snippet": sr.snippet, "pub_date": sr.pub_date,
        "rank": sr.rank, "created_at": sr.created_at,
    })


def _resolve_parents(con, source, conv_id, messages: list[ParsedMessage]) -> None:
    for msg in messages:
        if not msg.source_parent_id:
            continue
        new_child = id_map_repo.lookup(con, source, "message", msg.source_message_id)
        new_parent = id_map_repo.lookup(con, source, "message", msg.source_parent_id)
        if new_child is not None and new_parent is not None:
            messages_repo.resolve_parent(con, new_child, new_parent)


def _json(value) -> str | None:
    if not value:
        return None
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return None

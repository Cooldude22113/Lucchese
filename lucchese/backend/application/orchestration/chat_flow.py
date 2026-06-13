"""
application/orchestration/chat_flow.py
The chat workflow (Rule 3): order the intercepts, then run the normal RAG turn.

Produces a single async generator of NDJSON lines (meta / token / done) so the
route stays a one-liner. Intercept order is owned by command_detector; the LLM
provider branch is owned by llm_client; the wire format by stream_formatter.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from application.commands.command_detector import detect
from application.commands.memory_commands import handle_memory_command
from application.commands.roleplay_commands import ensure_session_started
from business_logic.meal_prep.shopify_meal_builder import add_meal
from business_logic.property.deal_calculator import analyse_deal
from business_logic.roleplay.roleplay_runner import run_roleplay
from config.model_settings import (
    ACTION_PLAN_MAX_TOKENS,
    CHAT_MAX_TOKENS,
    MODEL_DEEP,
    MODEL_FAST,
    SCRAPE_REVIEW_MAX_TOKENS,
)
from context.context_builder import build_context
from context.context_logging import emit_context_log
from context.context_result import ContextResult
from integrations.sheets.menu_context import get_menu_context
from memory.ingestion.exchange_ingestor import ingest_exchange
from memory.ingestion.ingest_policy import should_ingest
from memory.retrieval.semantic_search import search_memory
from model_runtime.clients import llm_client
from model_runtime.prompt_building.system_prompt_builder import build_system_prompt
from model_runtime.streaming.stream_formatter import done_line, meta_line, token_line
from storage.sqlite.repositories.message_repository import save_message
from web.scraping.page_fetcher import scrape_and_review
from web.search.ddgs_search import do_web_search
from web.search.search_decision import needs_web_search

_PERSONAL_SIGNALS = ["ptpreps", "my ", "i am", "i'm", "we ", "our ", "alex"]
_USER_CORRECTIONS = [
    "we already", "actually", "that's wrong", "not quite",
    "to clarify", "we don't", "we do", "i am", "i'm not",
]


def _plain_reply(conversation_id: str, reply: str, auto_ingested: bool = False):
    """Yield a complete single-reply NDJSON stream (meta + token + done)."""
    yield meta_line(conversation_id, web_search_used=False)
    yield token_line(reply)
    yield done_line(auto_ingested=auto_ingested)


async def stream_chat(req) -> AsyncIterator[str]:
    """Top-level chat generator: dispatch an intercept, else run the normal turn."""
    conversation_id = req.conversation_id or str(uuid.uuid4())
    kind, payload = detect(req.message, conversation_id)

    # ── Shopify intercept ─────────────────────────────────────────────────────
    if kind == "shopify":
        error, result = await add_meal(payload)
        reply = error if error else (
            f"Done! Created 4 products for {result['matched']} on Shopify:\n"
            + "".join(f"  ✓ {p['title']}\n" for p in result["created"])
        )
        for line in _plain_reply(conversation_id, reply):
            yield line
        return

    # ── Memory command intercept ──────────────────────────────────────────────
    if kind == "memory":
        command, content = payload
        reply = await handle_memory_command(command, content, conversation_id)
        save_message(conversation_id, "user", req.message)
        save_message(conversation_id, "assistant", reply)
        for line in _plain_reply(conversation_id, reply, auto_ingested=command == "remember"):
            yield line
        return

    # ── Deal analysis intercept ───────────────────────────────────────────────
    if kind == "deal":
        reply = analyse_deal(req.message)
        save_message(conversation_id, "user", req.message)
        save_message(conversation_id, "assistant", reply)
        for line in _plain_reply(conversation_id, reply):
            yield line
        return

    # ── Roleplay intercept ────────────────────────────────────────────────────
    if kind == "roleplay":
        ensure_session_started(req.message, conversation_id)
        reply = await run_roleplay(conversation_id, req.message, req.history)
        save_message(conversation_id, "user", req.message)
        save_message(conversation_id, "assistant", reply)
        for line in _plain_reply(conversation_id, reply):
            yield line
        return

    # ── Action plan intercept ─────────────────────────────────────────────────
    if kind == "action_plan":
        recent = await search_memory("website review ptpreps")
        action_prompt = f"""Based on this website review:

    {recent}

    Create a concrete action plan for Alex. Format it as a numbered list of specific tasks, ordered by impact. For each task include:
    - What exactly to change
    - Why it matters
    - How long it should take

    Focus on the highest ROI changes first. Be specific — no vague advice."""
        save_message(conversation_id, "user", req.message)
        messages = [
            {"role": "system", "content": build_system_prompt(None, "", "")},
            {"role": "user", "content": action_prompt},
        ]
        yield meta_line(conversation_id, web_search_used=False)
        full: list[str] = []
        try:
            async for token in llm_client.stream_tokens(
                messages, model=MODEL_FAST, max_tokens=ACTION_PLAN_MAX_TOKENS
            ):
                full.append(token)
                yield token_line(token)
        except Exception as e:
            yield token_line(f"Action plan error: {e}")
        reply = "".join(full)
        if reply:
            save_message(conversation_id, "assistant", reply)
        yield done_line(auto_ingested=False)
        return

    # ── Scrape intercept ──────────────────────────────────────────────────────
    if kind == "scrape":
        scrape_url = payload
        save_message(conversation_id, "user", req.message)
        review_prompt = await scrape_and_review(scrape_url)
        if review_prompt.startswith("Couldn't") or review_prompt.startswith("Failed"):
            save_message(conversation_id, "assistant", review_prompt)
            for line in _plain_reply(conversation_id, review_prompt):
                yield line
            return
        messages = [
            {"role": "system", "content": build_system_prompt(None, "", "")},
            {"role": "user", "content": review_prompt},
        ]
        yield meta_line(conversation_id, web_search_used=False)
        full = []
        try:
            async for token in llm_client.stream_tokens(
                messages, model=MODEL_FAST, max_tokens=SCRAPE_REVIEW_MAX_TOKENS
            ):
                full.append(token)
                yield token_line(token)
        except Exception as e:
            yield token_line(f"Review error: {e}")
        reply = "".join(full)
        if reply:
            save_message(conversation_id, "assistant", reply)
            await ingest_exchange(conversation_id, f"Website review: {scrape_url}", reply)
        yield done_line(auto_ingested=True)
        return

    # ── Normal chat flow ──────────────────────────────────────────────────────
    did_search = needs_web_search(req.message)
    web = await do_web_search(req.message) if did_search else ""
    has_personal = any(s in req.message.lower() for s in _PERSONAL_SIGNALS)
    if not did_search or has_personal:
        ctx = await build_context(req.message)
    else:
        ctx = ContextResult(
            tier1_status="empty_source",
            tier2_status="empty_source",
            tier1_char_count=0,
            tier2_char_count=0,
            tier2_result_count=0,
        )

    sheets = get_menu_context(req.message)
    emit_context_log(ctx, "chat", web, sheets)

    messages = [{"role": "system", "content": build_system_prompt(ctx, web, sheets)}]
    messages += req.history
    messages.append({"role": "user", "content": req.message})

    save_message(conversation_id, "user", req.message)

    yield meta_line(conversation_id, web_search_used=did_search)

    full = []
    model = MODEL_DEEP if req.deep else MODEL_FAST
    try:
        async for token in llm_client.stream_tokens(
            messages, model=model, max_tokens=CHAT_MAX_TOKENS
        ):
            full.append(token)
            yield token_line(token)
    except Exception as e:
        print(f"stream_response error: {e}")
        yield token_line("\n\n[Response error — please try again]")

    reply = "".join(full)
    auto_ingest = False
    if reply:
        save_message(conversation_id, "assistant", reply)
        force_ingest = any(s in req.message.lower() for s in _USER_CORRECTIONS)
        if force_ingest:
            auto_ingest = True
            await ingest_exchange(conversation_id, req.message, reply)
        elif not did_search:
            auto_ingest = should_ingest(req.message, reply)
            if auto_ingest:
                await ingest_exchange(conversation_id, req.message, reply)

    yield done_line(auto_ingested=auto_ingest)

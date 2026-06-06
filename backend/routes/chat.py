"""
routes/chat.py
──────────────
Main chat endpoint and its supporting logic:
  - Memory helpers (ingest, classify, dedup, search, RAG)
  - Explicit memory commands (remember / forget)
  - Web search
  - System prompt builder
  - POST /chat

Roleplay logic lives in routes/roleplay.py.
Deal analysis logic lives in routes/deal.py.
Shopify logic lives in routes/shopify.py.
"""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import httpx
import uuid
import re
import json
import asyncio
from datetime import datetime, timezone
from ddgs import DDGS
from routes.memory import search_memory, ingest_exchange, should_ingest, classify_memory, is_duplicate_memory, col_knowledge, col_facts, col_style, detect_memory_command, handle_memory_command, REMEMBER_PATTERNS, FORGET_PATTERNS
from routes.context_builder import build_context, ContextResult, emit_context_log
from routes.database import save_message, get_roleplay_session, upsert_roleplay_session
from routes.config import OLLAMA_URL, MODEL_FAST, MODEL_DEEP, ANTHROPIC_API_KEY, CHAT_PROVIDER
from sheets import get_menu_context
from routes.shopify import add_meal
from routes.roleplay import run_roleplay
from routes.scrape import detect_scrape_command, scrape_and_review


router = APIRouter()


class ChatRequest(BaseModel):
    message:         str
    history:         Optional[list] = []
    conversation_id: Optional[str]  = None
    deep:            Optional[bool] = False

WEB_TRIGGERS = [
    r"\b(latest|recent|current news|today|tonight)\b",
    r"\b(news|weather|score|results?|standings?)\b",
    r"\b(search|look up|google)\b",
    r"\b(released?|launched?|announced?)\b",
    r"\b(final|winner|champion|trophy)\b",
]

def needs_web_search(message: str) -> bool:
    msg = message.lower()


    if re.search(r'https?://|www\.|\.co\.uk|\.com|\.io', msg):
        return True
    
    internal_signals = [
        "macro", "recipe", "ingredient", "meal", "my ", "i am", "i'm",
        "analyse deal", "analyze deal", "practice pitch", "remember",
        "what have i", "what did i", "shopify",
    ]
    if any(s in msg for s in internal_signals):
        return False
    return any(re.search(p, msg) for p in WEB_TRIGGERS)



async def do_web_search(query: str, max_results: int = 4) -> str:
    try:
        results = await asyncio.to_thread(
            lambda: list(DDGS().text(query, max_results=max_results))
        )
        if not results:
            return ""
        lines = ["[Web search results:]"]
        for r in results:
            lines.append(f"• {r.get('title', '')}: {r.get('body', '')} ({r.get('href', '')})")
        return "\n".join(lines)
    except Exception:
        return ""


def build_system_prompt(ctx: ContextResult | None, web_context: str, sheets_context: str = "") -> str:
    """
    Assemble the full system prompt from a ContextResult and optional live data.

    ctx=None is treated as an empty context (scrape/action-plan flows).

    Section ordering:
      1. base persona
      2. Tier 1 — current-truth profile facts (if populated)
      3. Tier 2 — episodic/ChromaDB memory (if populated)
      4. Sheets live data (if present)
      5. Web search results (if present)
    """
    if ctx is None:
        ctx = ContextResult()

    base = """You are Lucchese, the personal AI of Alex Hammond.

Alex runs PTPreps — a meal prep business in the UK selling high protein meals in standard and bulking portions, available as one-time purchases or subscriptions via Shopify.
Alex is a personal trainer, into bodybuilding and martial arts, and is building this AI to automate his business and act as his most knowledgeable ally.

You know Alex well. Speak to him like a straight-talking, highly knowledgeable friend — not an assistant trying to please him.

Be direct and assertive. State things confidently without hedging.
Never use phrases like "it seems", "perhaps", "you might want to", "it could be", "I think", or "possibly" — if you know something, say it. If you don't, say so plainly.
Don't soften opinions or pad answers with disclaimers.
Don't be sycophantic — never open with praise or affirmations like "great question" or "absolutely".
When Alex is wrong or off track, say so directly and explain why. Challenge ideas that deserve to be challenged.
Match Alex's tone — casual, direct, no fluff.
Don't repeat yourself or over-explain.
Always end your response with a short, relevant question to keep the conversation moving.
Never guess or fabricate information about PTPreps, recipes, or macros — only use the Google Sheets data provided. If something isn't in the data, say so.
If you don't know something current like sports results, news, or prices — say so honestly.
When you use web search results, cite them naturally.
For ANY question about meals, ingredients, macros, or allergens — ONLY use the Google Sheets data provided. If a meal is not in the Sheets data, say "I don't have that meal in our current menu."
DOCUMENT GENERATION:
When the user asks you to write something as a document, Word doc, plan, programme, report,
or anything they'd want to save and use offline — generate the FULL content using proper
markdown structure. You MUST use markdown heading syntax:
  # Main Title
  ## Section Heading
  ### Subsection
  - bullet points for lists
  **bold** for key terms
  1. numbered steps where order matters

Then end your reply with exactly this marker on its own line:
[GENERATE_DOC: <short_descriptive_filename_no_extension>]
Example: [GENERATE_DOC: training_programme_week1]

IMPORTANT: Always use # and ## heading syntax. Never write section names as plain text.
Only use this marker when the content is genuinely document-worthy (structured plans,
programmes, checklists, reports). Not for short conversational answers."""

    sections = [base]

    if ctx.tier1_block:
        sections.append(f"""CURRENT FACTS ABOUT ALEX — TREAT AS GROUND TRUTH:
These are verified, up-to-date facts. Do not frame them as things Alex "mentioned" or "said".
Use them to ground every response.

If CURRENT FACTS conflict with BACKGROUND KNOWLEDGE, CURRENT FACTS always win.
BACKGROUND KNOWLEDGE may be historical and must not be treated as current unless it agrees with CURRENT FACTS.
Do not describe old courses, old goals, or old projects as current unless they appear in CURRENT FACTS.

{ctx.tier1_block}""")

    if ctx.tier2_block:
        sections.append(f"""BACKGROUND KNOWLEDGE ABOUT ALEX:
The following is drawn from Alex's past conversations. This is your existing knowledge of him — not something to report back, but something you already know.
Do NOT say "you mentioned" or "you said" or "you talked about". You simply know this about Alex.
Do NOT quote it back. Reason from it. Let it shape how you respond, what you assume, what you challenge.
If Alex asks what you know about a topic, answer as someone who already knows him — not as someone reading a file back to him.

--- Context ---
{ctx.tier2_block}

---""")

    if sheets_context:
        sections.append(f"""Live data from PTPREPS Google Sheets:
---
{sheets_context}
---
Use this for any questions about recipes, ingredients, macros, or allergens.""")

    if web_context:
        sections.append(f"""Current information from the web:
---
{web_context}
---
Use this data to inform your response. For website reviews, analyse what the search results reveal about the site's content, positioning, and copy.""")

    return "\n\n".join(sections)


@router.post("/chat")
async def chat(req: ChatRequest):
    conversation_id = req.conversation_id or str(uuid.uuid4())

    def stream_plain_reply(reply: str, web_search_used: bool = False, auto_ingested: bool = False):
        async def generator():
            yield json.dumps({"type": "meta", "conversation_id": conversation_id, "web_search_used": web_search_used}) + "\n"
            yield json.dumps({"type": "token", "content": reply}) + "\n"
            yield json.dumps({"type": "done",  "auto_ingested": auto_ingested}) + "\n"
        return StreamingResponse(generator(), media_type="application/x-ndjson")

    shopify_match = re.search(r'shopify add (.+)|add (.+) to shopify', req.message.lower())
    if shopify_match:
        meal_name = (shopify_match.group(1) or shopify_match.group(2)).strip()
        error, result = await add_meal(meal_name)
        reply = error if error else (
            f"Done! Created 4 products for {result['matched']} on Shopify:\n" +
            "".join(f"  ✓ {p['title']}\n" for p in result["created"])
        )
        return stream_plain_reply(reply)

    command, content = detect_memory_command(req.message)
    if command:
        reply = await handle_memory_command(command, content, conversation_id)
        save_message(conversation_id, "user", req.message)
        save_message(conversation_id, "assistant", reply)
        return stream_plain_reply(reply, auto_ingested=command == "remember")

    if req.message.lower().startswith(("analyse deal:", "analyze deal:")):
        from routes.deal import analyse_deal
        reply = analyse_deal(req.message)
        save_message(conversation_id, "user", req.message)
        save_message(conversation_id, "assistant", reply)
        return stream_plain_reply(reply)

    msg_lower          = req.message.lower().strip()
    is_active_roleplay = get_roleplay_session(conversation_id) is not None
    starts_roleplay    = any(x in msg_lower for x in [
        "practice pitch", "role play property", "roleplay property", "start practice"
    ])

    if starts_roleplay or is_active_roleplay:
        if starts_roleplay and not is_active_roleplay:
            upsert_roleplay_session(conversation_id, 0)
        reply = await run_roleplay(conversation_id, req.message, req.history)
        save_message(conversation_id, "user", req.message)
        save_message(conversation_id, "assistant", reply)
        return stream_plain_reply(reply)

    if req.message.lower().strip() in ["action plan", "action plan.", "action plan!"]:
        recent = await search_memory("website review ptpreps")
        action_prompt = f"""Based on this website review:

    {recent}

    Create a concrete action plan for Alex. Format it as a numbered list of specific tasks, ordered by impact. For each task include:
    - What exactly to change
    - Why it matters
    - How long it should take

    Focus on the highest ROI changes first. Be specific — no vague advice."""
        save_message(conversation_id, "user", req.message)
        action_messages = [
            {"role": "system", "content": build_system_prompt(None, "", "")},
            {"role": "user", "content": action_prompt}
        ]
        async def action_stream():
            full = []
            yield json.dumps({"type": "meta", "conversation_id": conversation_id, "web_search_used": False}) + "\n"
            try:
                if CHAT_PROVIDER == "claude":
                    async with httpx.AsyncClient(timeout=300) as client:
                        res = await client.post(
                            "https://api.anthropic.com/v1/messages",
                            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                            json={"model": "claude-sonnet-4-6", "max_tokens": 4096, "system": action_messages[0]["content"], "messages": [action_messages[1]]}
                        )
                    text = res.json()["content"][0]["text"]
                    full.append(text)
                    yield json.dumps({"type": "token", "content": text}) + "\n"
                else:
                    async with httpx.AsyncClient(timeout=300) as client:
                        async with client.stream("POST", OLLAMA_URL, json={"model": MODEL_FAST, "messages": action_messages, "stream": True}) as response:
                            async for line in response.aiter_lines():
                                if not line.strip(): continue
                                try:
                                    chunk = json.loads(line)
                                    token = chunk.get("message", {}).get("content", "")
                                    if token:
                                        full.append(token)
                                        yield json.dumps({"type": "token", "content": token}) + "\n"
                                    if chunk.get("done"): break
                                except Exception: continue
            except Exception as e:
                yield json.dumps({"type": "token", "content": f"Action plan error: {e}"}) + "\n"
            reply = "".join(full)
            if reply:
                save_message(conversation_id, "assistant", reply)
            yield json.dumps({"type": "done", "auto_ingested": False}) + "\n"
        return StreamingResponse(action_stream(), media_type="application/x-ndjson")

    scrape_url = detect_scrape_command(req.message)
    if scrape_url:
        save_message(conversation_id, "user", req.message)
        review_prompt = await scrape_and_review(scrape_url)
        if review_prompt.startswith("Couldn't") or review_prompt.startswith("Failed"):
            save_message(conversation_id, "assistant", review_prompt)
            return stream_plain_reply(review_prompt)
        scrape_messages = [
            {"role": "system", "content": build_system_prompt(None, "", "")},
            {"role": "user", "content": review_prompt}
        ]
        async def scrape_stream():
            full = []
            yield json.dumps({"type": "meta", "conversation_id": conversation_id, "web_search_used": False}) + "\n"
            try:
                if CHAT_PROVIDER == "claude":
                    async with httpx.AsyncClient(timeout=300) as client:
                        res = await client.post(
                            "https://api.anthropic.com/v1/messages",
                            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                            json={"model": "claude-sonnet-4-6", "max_tokens": 4096, "system": scrape_messages[0]["content"], "messages": [scrape_messages[1]]}
                        )
                    text = res.json()["content"][0]["text"]
                    full.append(text)
                    yield json.dumps({"type": "token", "content": text}) + "\n"
                else:
                    async with httpx.AsyncClient(timeout=300) as client:
                        async with client.stream("POST", OLLAMA_URL, json={"model": MODEL_FAST, "messages": scrape_messages, "stream": True}) as response:
                            async for line in response.aiter_lines():
                                if not line.strip(): continue
                                try:
                                    chunk = json.loads(line)
                                    token = chunk.get("message", {}).get("content", "")
                                    if token:
                                        full.append(token)
                                        yield json.dumps({"type": "token", "content": token}) + "\n"
                                    if chunk.get("done"): break
                                except Exception: continue
            except Exception as e:
                yield json.dumps({"type": "token", "content": f"Review error: {e}"}) + "\n"
            reply = "".join(full)
            if reply:
                save_message(conversation_id, "assistant", reply)
                await ingest_exchange(
                    conversation_id,
                    f"Website review: {scrape_url}",
                    reply
                )
            yield json.dumps({"type": "done", "auto_ingested": True}) + "\n"
        return StreamingResponse(scrape_stream(), media_type="application/x-ndjson")

    did_search = needs_web_search(req.message)
    web        = await do_web_search(req.message) if did_search else ""
    _personal_signals = ["ptpreps", "my ", "i am", "i'm", "we ", "our ", "alex"]
    _has_personal      = any(s in req.message.lower() for s in _personal_signals)
    ctx = await build_context(req.message) if (not did_search or _has_personal) else ContextResult(
        tier1_status="empty_source",
        tier2_status="empty_source",
        tier1_char_count=0,
        tier2_char_count=0,
        tier2_result_count=0,
    )

    sheets     = get_menu_context(req.message)

    emit_context_log(ctx, "chat", web, sheets)

    messages = [{"role": "system", "content": build_system_prompt(ctx, web, sheets)}]
    messages += req.history
    messages.append({"role": "user", "content": req.message})

    save_message(conversation_id, "user", req.message)

    async def stream_response():
        full_reply  = []
        auto_ingest = False

        yield json.dumps({
            "type":            "meta",
            "conversation_id": conversation_id,
            "web_search_used": did_search,
        }) + "\n"

        try:
            if CHAT_PROVIDER == "claude":
                system_prompt = messages[0]["content"] if messages[0]["role"] == "system" else ""
                chat_messages = [m for m in messages if m["role"] != "system"]
                async with httpx.AsyncClient(timeout=300) as client:
                    res = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key":         ANTHROPIC_API_KEY,
                            "anthropic-version": "2023-06-01",
                            "content-type":      "application/json",
                        },
                        json={
                            "model":      "claude-sonnet-4-6",
                            "max_tokens": 4096,
                            "system":     system_prompt,
                            "messages":   chat_messages,
                        }
                    )
                if res.status_code != 200:
                    raise Exception(f"Anthropic API error {res.status_code}: {res.text[:200]}")
                reply_text = res.json()["content"][0]["text"]
                full_reply.append(reply_text)
                yield json.dumps({"type": "token", "content": reply_text}) + "\n"

            else:
                async with httpx.AsyncClient(timeout=300) as client:
                    async with client.stream("POST", OLLAMA_URL, json={
                        "model":    MODEL_DEEP if req.deep else MODEL_FAST,
                        "messages": messages,
                        "stream":   True,
                    }) as response:
                        async for line in response.aiter_lines():
                            if not line.strip():
                                continue
                            try:
                                chunk = json.loads(line)
                                token = chunk.get("message", {}).get("content", "")
                                if token:
                                    full_reply.append(token)
                                    yield json.dumps({"type": "token", "content": token}) + "\n"
                                if chunk.get("done"):
                                    break
                            except Exception:
                                continue

        except Exception as e:
            print(f"stream_response error ({CHAT_PROVIDER}): {e}")
            yield json.dumps({"type": "token", "content": "\n\n[Response error — please try again]"}) + "\n"

        reply = "".join(full_reply)
        if reply:
            save_message(conversation_id, "assistant", reply)

            user_corrections = [
                "we already", "actually", "that's wrong", "not quite",
                "to clarify", "we don't", "we do", "i am", "i'm not"
            ]
            force_ingest = any(s in req.message.lower() for s in user_corrections)

            if force_ingest:
                auto_ingest = True
                await ingest_exchange(conversation_id, req.message, reply)
            elif not did_search:
                auto_ingest = should_ingest(req.message, reply)
                if auto_ingest:
                    await ingest_exchange(conversation_id, req.message, reply)

        yield json.dumps({"type": "done", "auto_ingested": auto_ingest}) + "\n"

    return StreamingResponse(stream_response(), media_type="application/x-ndjson")
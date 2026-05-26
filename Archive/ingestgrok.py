"""
ingest_grok_v1.py
─────────────────
Lean ingestion of Grok exports into ChromaDB for Lucchese.
Matches the v9 ChatGPT ingest architecture exactly.

GROK EXPORT FORMAT (prod-grok-backend.json):
  Top-level keys: conversations, projects, tasks, media_posts
  Each conversation:
    conversation.create_time  → plain ISO string with Z suffix
    conversation.id, .title
    responses[]               → flat list of ALL responses (incl. regenerated branches)
      response._id            → unique response ID
      response.parent_response_id → parent in tree (None for root)
      response.sender         → 'human', 'ASSISTANT', or 'assistant'
      response.message        → text content (may contain <grok:render> XML tags)
      response.create_time    → {'$date': {'$numberLong': 'ms_epoch_string'}}

KEY DIFFERENCES FROM CHATGPT INGEST:
  - No current_node: leaf_response_id is always None in Grok exports.
    Accepted path is found by locating the leaf with the highest timestamp
    and walking backwards via parent_response_id links.
  - 21 of 208 conversations have branching (regenerated responses).
  - Sender variants: 'human', 'ASSISTANT', 'assistant' — normalised with .lower()
  - <grok:render ...> citation tags must be stripped from assistant messages.
  - Conversation timestamps are plain ISO+Z; message timestamps are MongoDB epoch.
  - All 210 conversations are 2025-11-11 to 2026-04-22 (all "present" era),
    but era mention extraction still runs to catch Alex referencing the past.
  - media_posts (image generations) are ignored entirely.

ARCHITECTURE (matches ingest_chatgpt_v9.py):
  - Embeds user_text only — assistant stored as metadata (no vector contamination)
  - user_text_raw in metadata for serving layer (document may have [prior:] prefix)
  - assistant_excerpt: 600 chars, preamble-stripped
  - Accepted path traversal via reverse walk from highest-timestamp leaf
  - Deterministic noise filter — no LLM gate
  - Conversation summaries (1 LLM call per conversation)
  - Era mention extraction (regex-gated, ~0.5 LLM calls per conversation)
  - Distance logging only — no dedup at ingest (deferred to reclassify.py)
  - Checkpoint system — safe to resume on interrupt
  - threading.Lock on all ChromaDB mutations
  - facts and style deferred to reclassify.py

WORKFLOW:
  1. Run ChatGPT ingest first (already done)
  2. Run this script (adds to existing knowledge collection)
  3. reclassify.py handles routing, taxonomy, ontology, dedup
  4. Admin panel → Manage → Rebuild Summaries

USAGE:
  python ingest_grok_v1.py --input "C:/path/to/prod-grok-backend.json"
  python ingest_grok_v1.py --input "C:/path/to/prod-grok-backend.json" --wipe
  python ingest_grok_v1.py --input "C:/path/to/prod-grok-backend.json" --limit 20
"""

import json
import argparse
import logging
import re
import threading
import uuid
import asyncio
import hashlib
import httpx
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
CHROMA_PATH   = "./chroma_db"
EMBED_MODEL   = "nomic-ai/nomic-embed-text-v1"
CHUNK_SIZE    = 800
CHUNK_OVERLAP = 100
BATCH_SIZE    = 10
CONCURRENCY   = 4

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/api/chat"
MODEL      = os.getenv("MODEL_FAST", "gemma2:27b")

# Distance logging — no filtering at ingest (same as v9).
# Dedup happens in reclassify.py after taxonomy is known.
_all_dedup_distances: list[float] = []

# threading.Lock for all ChromaDB mutations.
# asyncio.Lock is NOT thread-safe from asyncio.to_thread pool.
_chroma_lock = threading.Lock()

# ── Era boundaries (same as v9) ───────────────────────────────────────────────
ERA_BOUNDARIES = [
    (None, 2013, "pre_divorce"),
    (2013, 2020, "post_divorce"),
    (2020, 2022, "transition"),
    (2022, 2024, "building"),
    (2024, None, "present"),
]

def get_era_from_year(year: int) -> str:
    for start, end, label in ERA_BOUNDARIES:
        if (start is None or year >= start) and (end is None or year < end):
            return label
    return "present"


# ── Logging ───────────────────────────────────────────────────────────────────
_log_path = Path(f"ingest_grok_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
_file_handler    = logging.FileHandler(_log_path, encoding="utf-8")
_console_handler = logging.StreamHandler()
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_console_handler.setLevel(logging.WARNING)
_console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
log = logging.getLogger("lucchese_grok_ingest")
log.setLevel(logging.DEBUG)
log.addHandler(_file_handler)
log.addHandler(_console_handler)


# ── ChromaDB setup ────────────────────────────────────────────────────────────
def get_collections():
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL,
        trust_remote_code=True
    )
    client        = chromadb.PersistentClient(path=CHROMA_PATH)
    col_knowledge = client.get_or_create_collection("knowledge",  embedding_function=ef)
    col_summaries = client.get_or_create_collection("summaries",  embedding_function=ef)
    # facts and style NOT written at ingest — populated by reclassify.py
    return client, ef, col_knowledge, col_summaries


# ── Text chunking ─────────────────────────────────────────────────────────────
def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks    = []
    current   = ""

    for sentence in sentences:
        if len(sentence) > size:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(sentence), size - overlap):
                part = sentence[i:i + size]
                if part.strip():
                    chunks.append(part.strip())
            continue

        if len(current) + len(sentence) + 1 <= size:
            current = (current + " " + sentence).strip()
        else:
            if current:
                chunks.append(current)
                overlap_seed = current[-overlap:].strip()
                seeded = (overlap_seed + " " + sentence).strip()
                current = seeded if len(seeded) <= size else sentence
            else:
                current = sentence

    if current:
        chunk_hash = hashlib.md5(current.encode()).hexdigest()
        existing_hashes = {hashlib.md5(c.encode()).hexdigest() for c in chunks}
        if chunk_hash not in existing_hashes:
            chunks.append(current)

    return [c for c in chunks if len(c.strip()) > 20]


# ── Timestamp helpers ─────────────────────────────────────────────────────────
def parse_conv_timestamp(ts) -> str:
    """
    Conversation-level timestamps are plain ISO strings with Z suffix.
    e.g. '2025-11-11T15:57:16.618539Z'
    """
    if isinstance(ts, str) and ts:
        # fromisoformat() requires +00:00 not Z in Python < 3.11
        return ts.replace("Z", "+00:00")
    return ""

def parse_message_timestamp(ts) -> str:
    """
    Message-level timestamps are MongoDB extended JSON.
    e.g. {'$date': {'$numberLong': '1762876636645'}}
    All 2646 messages in the export have this format — no missing timestamps.
    """
    if isinstance(ts, dict):
        inner = ts.get("$date", {})
        if isinstance(inner, dict):
            ms_str = inner.get("$numberLong", "")
            if ms_str:
                try:
                    ms = int(ms_str)
                    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
                except (ValueError, OSError):
                    log.warning(f"parse_message_timestamp: invalid ms value '{ms_str}'")
    return ""

def year_from_iso(iso: str) -> int:
    try:
        return datetime.fromisoformat(iso).year
    except Exception:
        return datetime.now().year


# ── Grok message cleaning ─────────────────────────────────────────────────────
# 166 of 2646 responses contain <grok:render ...> citation tags.
# These are inline citation markers Grok inserts — not part of the text content.
# Strip them before embedding or storing.
_GROK_TAG_RE = re.compile(r"<grok:[^>]+>.*?</grok:[^>]+>", re.DOTALL)

def clean_grok_message(text: str) -> str:
    """Strip <grok:render> citation tags and normalise whitespace."""
    if not text:
        return ""
    cleaned = _GROK_TAG_RE.sub("", text)
    # Collapse multiple blank lines left by tag removal
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


# ── Message extraction — accepted path only ───────────────────────────────────
def extract_messages_accepted_path(responses: list) -> list:
    """
    Grok exports include ALL responses (branching included) as a flat list.
    leaf_response_id is always None — no shortcut to the accepted path.

    Strategy:
    1. Build id → response map and parent → children map.
    2. Find leaf nodes (no children).
    3. If multiple leaves (branching), pick the one with the highest timestamp.
       This is the most recently accepted response — the path the user chose.
    4. Walk backwards via parent_response_id links to the root.
    5. Reverse to get chronological order.

    21 of 208 conversations have branching. 187 are linear (single leaf).
    For linear conversations this is equivalent to using the responses in order.
    """
    if not responses:
        return []

    # Build maps
    id_to_resp = {}
    children_of: dict[str, list[str]] = {}

    for r in responses:
        resp = r.get("response", {})
        rid  = resp.get("_id")
        pid  = resp.get("parent_response_id")
        if not rid:
            continue
        id_to_resp[rid] = resp
        children_of.setdefault(pid, [])      # register parent slot
        children_of.setdefault(rid, [])      # register self slot
        if pid:
            children_of[pid].append(rid)

    all_ids = set(id_to_resp.keys())

    # Leaves = responses that have no children in this conversation
    leaf_ids = [rid for rid in all_ids if not children_of.get(rid)]

    if not leaf_ids:
        log.warning("extract_messages: no leaf found — using last response as fallback")
        leaf_ids = [responses[-1]["response"]["_id"]] if responses else []

    # Pick leaf with highest message timestamp (most recently accepted path)
    def leaf_epoch(rid: str) -> int:
        ct = id_to_resp.get(rid, {}).get("create_time", {})
        if isinstance(ct, dict):
            inner = ct.get("$date", {})
            if isinstance(inner, dict):
                return int(inner.get("$numberLong", 0))
        return 0

    leaf_id = max(leaf_ids, key=leaf_epoch)

    if len(leaf_ids) > 1:
        log.debug(
            f"extract_messages: {len(leaf_ids)} leaves found (branching) "
            f"— selected leaf {leaf_id[:8]} with highest timestamp"
        )

    # Walk backwards from leaf to root
    path: list[dict] = []
    node_id: str | None = leaf_id
    visited: set[str] = set()

    while node_id and node_id not in visited:
        visited.add(node_id)
        resp = id_to_resp.get(node_id)
        if resp:
            path.append(resp)
        node_id = resp.get("parent_response_id") if resp else None

    path.reverse()  # root → leaf

    # Extract user/assistant messages, cleaning grok XML tags
    messages = []
    for resp in path:
        sender = resp.get("sender", "").lower()
        role   = "user" if sender == "human" else "assistant" if sender in ("assistant",) else None
        if role is None:
            continue  # skip system/tool roles if they appear

        raw_msg = resp.get("message") or ""
        text    = clean_grok_message(raw_msg)
        ts      = parse_message_timestamp(resp.get("create_time", {}))

        if text:
            messages.append({"role": role, "text": text, "timestamp": ts})

    log.debug(f"extract_messages: accepted path {len(path)} nodes → {len(messages)} messages")
    return messages


def build_exchange_pairs(messages: list) -> tuple[list, int]:
    """Returns (pairs, dropped_count). Same logic as v9."""
    pairs   = []
    dropped = 0
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg["role"] == "user":
            user_text      = msg["text"]
            user_ts        = msg["timestamp"]
            assistant_text = ""
            if i + 1 < len(messages) and messages[i + 1]["role"] == "assistant":
                assistant_text = messages[i + 1]["text"]
                i += 1
            pairs.append({
                "user_text":      user_text,
                "assistant_text": assistant_text,
                "timestamp":      user_ts,
            })
        elif msg["role"] == "assistant":
            dropped += 1
        i += 1
    return pairs, dropped


# ── Preamble stripper ─────────────────────────────────────────────────────────
def _strip_preamble(text: str, min_words: int = 12) -> str:
    """Strip short preamble sentences from assistant responses."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    for i, s in enumerate(sentences):
        if len(s.split()) >= min_words:
            return " ".join(sentences[i:])
    return text


# ── Deterministic noise filter ────────────────────────────────────────────────
_ARTEFACT_PATTERNS = [
    r"\bgenerate\b.{0,20}\bimage\b",
    r"\bmake.{0,20}(less blurry|clearer|sharper)\b",
    r"\bcreate\b.{0,20}\b(logo|banner|thumbnail|image)\b",
    r"\bdraw\b.{0,30}\b(picture|image|illustration)\b",
]

def noise_filter(conv_meta: dict, pairs: list) -> tuple[bool, str]:
    """
    Returns (passes, reason). Deterministic only — no LLM.
    Fails closed only on clear garbage. Everything uncertain passes.
    Total word count checked BEFORE title check so substantive conversations
    are never dropped just because of a default or generic title.
    """
    title = conv_meta.get("title", "").strip().lower()

    if not pairs:
        return False, "no exchange pairs"

    # Single exchange, minimal content on both sides
    if len(pairs) == 1:
        user_words      = len(pairs[0]["user_text"].split())
        assistant_words = len(pairs[0]["assistant_text"].split())
        if user_words < 8 and assistant_words < 15:
            return False, "single exchange with minimal content"

    # Total user word count — veto power before title check
    total_user_words = sum(len(p["user_text"].split()) for p in pairs)
    if total_user_words < 12:
        return False, f"user content too thin ({total_user_words} total words)"

    # Test/greeting titles — only filter if title is generic AND content is thin
    test_titles = {"test", "hello", "hi", "testing", "hey", "untitled", "new conversation"}
    if title in test_titles:
        first_user = pairs[0]["user_text"].strip().lower()
        if len(first_user.split()) <= 3 and total_user_words < 30:
            return False, "test or greeting message"

    # Pure image/artefact generation
    non_empty = [p for p in pairs if p["user_text"].strip()]
    if non_empty and all(
        any(re.search(pat, p["user_text"].lower()) for pat in _ARTEFACT_PATTERNS)
        for p in non_empty
    ):
        return False, "pure image/artefact generation conversation"

    return True, "passes noise filter"


# ── LLM call ─────────────────────────────────────────────────────────────────
_semaphore: asyncio.Semaphore | None = None

async def llm_call(client: httpx.AsyncClient, prompt: str, max_tokens: int = 100) -> str:
    assert _semaphore is not None, "semaphore not initialised"
    async with _semaphore:
        for attempt in range(3):
            try:
                res = await client.post(
                    OLLAMA_URL,
                    json={
                        "model":    MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream":   False,
                        "options":  {"temperature": 0, "num_predict": max_tokens},
                    },
                    timeout=90,
                )
                return res.json()["message"]["content"].strip()
            except Exception as e:
                log.warning(f"LLM attempt {attempt+1}/3 failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
        log.error("LLM call failed after 3 attempts")
        return ""

def safe_json(text: str) -> dict:
    """Parse JSON from LLM response. Handles Gemma preamble and markdown fences."""
    try:
        clean = re.sub(r"```json|```", "", text).strip()
        clean = re.sub(r",\s*([}\]])", r"\1", clean)
        return json.loads(clean)
    except Exception:
        pass
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            clean = re.sub(r",\s*([}\]])", r"\1", match.group(0))
            return json.loads(clean)
    except Exception:
        pass
    log.warning(f"safe_json: parse failure — raw: '{text[:120]}'")
    return {}


# ── Era extraction ────────────────────────────────────────────────────────────
TEMPORAL_SIGNALS = [
    "years ago", "back in", "when i was",
    "a few years", "decade ago",
    "growing up", "as a kid", "as a child",
    "in the past", "back then",
]

ERA_PROMPT = """Does this text reference a specific time period or relative time?
Examples: "10 years ago", "back in 2019", "when I was younger"

Text: {text}

Reply with JSON only:
{{"has_time_ref": true, "approximate_year": 2015}}
or
{{"has_time_ref": false, "approximate_year": null}}"""

async def extract_era_mention(client: httpx.AsyncClient, pairs: list) -> tuple[bool, int | None]:
    all_user_text = " ".join(p["user_text"] for p in pairs)
    t = all_user_text.lower()

    match_pos = -1
    for sig in TEMPORAL_SIGNALS:
        idx = t.find(sig)
        if idx != -1 and (match_pos == -1 or idx < match_pos):
            match_pos = idx

    if match_pos == -1:
        return False, None

    window_start = max(0, match_pos - 200)
    text_window  = all_user_text[window_start:window_start + 1000]

    prompt   = ERA_PROMPT.format(text=text_window)
    response = await llm_call(client, prompt, max_tokens=40)
    result   = safe_json(response)

    has_ref = result.get("has_time_ref", False)
    year    = result.get("approximate_year", None)

    if isinstance(year, int) and 1980 <= year <= datetime.now().year:
        return has_ref, year
    return False, None


# ── Conversation summary ──────────────────────────────────────────────────────
SUMMARY_PROMPT = """Write one sentence describing this conversation and what it reveals about Alex.
Be specific. Start with the topic itself, not with "Alex" or "This conversation".

Good example: "Property deal analysis for a two-bed flat in Manchester exploring
yield vs capital growth, showing Alex stress-testing numbers before committing."

Title: {title}
Exchanges ({n} total — weighted toward the final exchanges where positions develop):
{sample}

One sentence only:"""

def _sample_for_summary(pairs: list, max_samples: int = 6) -> list:
    n = len(pairs)
    if n <= max_samples:
        return pairs
    indices = [0]
    mid = n // 2
    indices.append(mid)
    final_third_start = max(mid + 1, n - 4)
    indices += list(range(final_third_start, n))
    seen   = set()
    result = []
    for idx in indices:
        if idx not in seen and 0 <= idx < n:
            seen.add(idx)
            result.append(idx)
        if len(result) >= max_samples:
            break
    return [pairs[i] for i in sorted(result)]

async def generate_summary(
    client: httpx.AsyncClient,
    conv_id: str,
    title: str,
    pairs: list,
    col_summaries,
) -> str:
    sampled = _sample_for_summary(pairs)
    sample  = "\n".join([
        f"[Alex]: {p['user_text'][:200]}\n[Grok]: {p['assistant_text'][:100]}"
        for p in sampled
    ])
    prompt  = SUMMARY_PROMPT.format(title=title, n=len(pairs), sample=sample)
    summary = (await llm_call(client, prompt, max_tokens=80)).strip()

    if summary:
        def _upsert():
            with _chroma_lock:
                col_summaries.upsert(
                    ids       = [f"grok_summary_{conv_id}"],
                    documents = [summary],
                    metadatas = [{
                        "source":  "grok",
                        "conv_id": conv_id,
                        "title":   title,
                        "type":    "conv_summary",
                    }],
                )
        await asyncio.to_thread(_upsert)
        log.debug(f"SUMMARY [{conv_id}]: {summary[:80]}")

    return summary


# ── Distance logging (calibration only — no filtering at ingest) ──────────────
def _log_dedup_distance_sync(text: str, collection) -> None:
    """Log nearest-neighbour distance for calibration. Never skips content."""
    try:
        results = collection.query(
            query_texts = [text],
            n_results   = 1,
            include     = ["distances"],
        )
        if not results["distances"] or not results["distances"][0]:
            return
        dist = results["distances"][0][0]
        _all_dedup_distances.append(dist)
        log.debug(f"DEDUP [INFO ONLY]: dist={dist:.4f} — not used for filtering at ingest")
    except Exception as e:
        log.error(f"DEDUP distance logging error: {e}")

async def log_dedup_distance(text: str, collection) -> None:
    await asyncio.to_thread(_log_dedup_distance_sync, text, collection)


# ── Process single conversation ───────────────────────────────────────────────
async def process_conversation(
    conv: dict,
    client: httpx.AsyncClient,
    col_knowledge,
    col_summaries,
    stats: dict,
    increment_stat,
) -> None:

    conv_meta = conv.get("conversation", {})
    conv_id   = conv_meta.get("id", str(uuid.uuid4()))
    title     = conv_meta.get("title", "Untitled")
    created   = parse_conv_timestamp(conv_meta.get("create_time", ""))
    responses = conv.get("responses", [])

    if not responses:
        await increment_stat("skipped")
        log.debug(f"SKIP [{conv_id}]: no responses")
        return

    messages       = extract_messages_accepted_path(responses)
    pairs, dropped = build_exchange_pairs(messages)

    if dropped:
        log.debug(f"[{conv_id}]: {dropped} orphaned assistant message(s) dropped")

    # ── Deterministic noise filter ────────────────────────────────────────────
    passes, reason = noise_filter(conv_meta, pairs)
    if not passes:
        await increment_stat("noise_filtered")
        print(f"  ✗ [{title[:55]}] — {reason}")
        log.info(f"NOISE_FILTER [{conv_id}] title='{title[:60]}' reason='{reason}'")
        return

    # ── Conversation-level metadata ───────────────────────────────────────────
    conv_year = year_from_iso(created) if created else datetime.now().year
    conv_era  = get_era_from_year(conv_year)

    # Run era extraction and summary concurrently
    (has_era_ref, ref_year), conv_summary = await asyncio.gather(
        extract_era_mention(client, pairs),
        generate_summary(client, conv_id, title, pairs, col_summaries),
    )

    if ref_year is None:
        has_era_ref = False
    referenced_era = get_era_from_year(ref_year) if ref_year else ""

    print(f"  ✓ [{title[:55]}] {conv_era}")
    log.info(f"PROCESSING [{conv_id}] title='{title}' era={conv_era} pairs={len(pairs)}")

    # ── Process each exchange pair ────────────────────────────────────────────
    for j, pair in enumerate(pairs):
        user_text      = pair["user_text"].strip()
        assistant_text = pair["assistant_text"].strip()

        if not user_text:
            continue

        if len(user_text.split()) < 5:
            log.debug(f"SKIP exchange {j} [{conv_id}] — user text below 5 words")
            continue

        # Context seed for short messages
        prev_user_text = pairs[j - 1]["user_text"] if j > 0 else ""
        if len(user_text.split()) < 15 and prev_user_text:
            embed_text = f"[prior: {prev_user_text[:100]}] {user_text}"
        else:
            embed_text = user_text

        # Log distance for calibration
        await log_dedup_distance(embed_text, col_knowledge)

        # Assistant excerpt
        assistant_excerpt = _strip_preamble(assistant_text)[:600]
        assistant_length  = len(assistant_text)

        # Metadata
        base_meta = {
            "source":             "grok",
            "conv_id":            conv_id,
            "title":              title,
            "created_at":         created,
            "conv_year":          str(conv_year),
            "era":                conv_era,
            "pair_idx":           str(j),
            "has_era_mention":    str(has_era_ref).lower(),
            "referenced_era":     referenced_era,
            "conv_summary":       conv_summary[:200] if conv_summary else "",
            "user_text_raw":      user_text,        # clean user text — serving layer reads this
            "assistant_excerpt":  assistant_excerpt,  # preamble-stripped, 600 chars
            "assistant_length":   assistant_length,
            "type":               "knowledge",
            # Fields populated by reclassify.py — placeholders only
            "category":           "unclassified",
            "ontology":           "unclassified",
            "source_type":        "unclassified",
            "primary_tier1":      "unclassified",
            "primary_tier2":      "unclassified",
            "primary_tier3":      "unclassified",
            "secondary_tier1":    "",
            "secondary_tier2":    "",
            "secondary_tier3":    "",
            "is_personal":        "unclassified",
            "engagement":         "unclassified",
            "routing_done":       "false",
        }

        # Chunk and store
        # Document = embed_text (may have [prior:] prefix).
        # Serving layer reads user_text_raw from metadata for display.
        for k, chunk in enumerate(chunk_text(embed_text)):
            chunk_meta = {**base_meta, "chunk_idx": str(k)}

            def _upsert_knowledge(meta=chunk_meta, doc=chunk):
                with _chroma_lock:
                    col_knowledge.upsert(
                        ids       = [f"grok_know_{conv_id}_{j}_{k}"],
                        documents = [doc],
                        metadatas = [meta],
                    )

            await asyncio.to_thread(_upsert_knowledge)
            await increment_stat("knowledge")

    await increment_stat("processed")


# ── Wipe ──────────────────────────────────────────────────────────────────────
def wipe_grok_entries(col_knowledge, col_summaries, checkpoint_path: Path):
    """
    Wipes all grok-sourced entries from ChromaDB.
    Also clears checkpoint file.
    Note: does NOT pass include=["ids"] — "ids" is not a valid ChromaDB include
    value and causes silent wipe failure on ChromaDB >= 0.4.x.
    """
    print("Wiping existing Grok entries...")
    FETCH_SIZE = 500
    max_iters  = 200

    for col in [col_knowledge, col_summaries]:
        try:
            all_ids = []
            offset  = 0
            iters   = 0
            while iters < max_iters:
                results = col.get(
                    where  = {"source": "grok"},
                    limit  = FETCH_SIZE,
                    offset = offset,
                )
                if not results["ids"]:
                    break
                all_ids.extend(results["ids"])
                offset += FETCH_SIZE
                iters  += 1
            if iters >= max_iters:
                log.error(f"WIPE: max iterations reached for '{col.name}'")
            if all_ids:
                col.delete(ids=all_ids)
                print(f"  Deleted {len(all_ids)} from '{col.name}'")
            else:
                print(f"  Nothing to delete in '{col.name}'")
        except Exception as e:
            log.error(f"WIPE error '{col.name}': {e}")
            print(f"  Wipe error '{col.name}': {e}")

    if checkpoint_path.exists():
        checkpoint_path.unlink()
        print("  Checkpoint cleared")
        log.info("WIPE: checkpoint cleared")


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    global _semaphore

    parser = argparse.ArgumentParser(description="Lucchese Grok Ingest v1")
    parser.add_argument("--input",         required=True, help="Path to prod-grok-backend.json")
    parser.add_argument("--wipe",          action="store_true")
    parser.add_argument("--limit",         type=int, default=None)
    parser.add_argument("--no-checkpoint", action="store_true")
    args = parser.parse_args()

    _semaphore = asyncio.Semaphore(CONCURRENCY)

    stats_lock = asyncio.Lock()
    stats = {
        "processed":      0,
        "skipped":        0,
        "noise_filtered": 0,
        "knowledge":      0,
    }

    async def increment_stat(key: str, n: int = 1):
        async with stats_lock:
            stats[key] = stats.get(key, 0) + n

    checkpoint_path = Path("ingest_grok_checkpoint.json")

    print(f"\n{'─'*60}")
    print(f"Lucchese Grok Ingest v1")
    print(f"Model      : {MODEL}")
    print(f"Concurrency: {CONCURRENCY}")
    print(f"Batch size : {BATCH_SIZE}")
    print(f"Embeds     : user_text only (assistant stored as metadata)")
    print(f"Gate       : deterministic code only (no LLM gate)")
    print(f"Routing    : deferred to reclassify.py")
    print(f"Input      : {args.input}")
    print(f"Log        : {_log_path}")
    print(f"{'─'*60}\n")

    log.info(f"=== GROK INGEST START === model={MODEL} input={args.input}")

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    async with httpx.AsyncClient() as client:
        try:
            await client.get(base_url, timeout=5)
            print("✓ Ollama reachable\n")
        except Exception:
            print("✗ Ollama unreachable — is it running?")
            log.error(f"Ollama unreachable at {base_url}")
            return

        _, _, col_knowledge, col_summaries = get_collections()

        if args.wipe:
            wipe_grok_entries(col_knowledge, col_summaries, checkpoint_path)
            print()

        # Load checkpoint
        processed_ids: set[str] = set()
        if not args.no_checkpoint and checkpoint_path.exists():
            try:
                processed_ids = set(json.loads(checkpoint_path.read_text()))
                print(f"Checkpoint: {len(processed_ids)} conversations already processed\n")
                log.info(f"CHECKPOINT: loaded {len(processed_ids)} IDs")
            except Exception as e:
                log.warning(f"CHECKPOINT: failed to load — {e}")

        # Load export
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"Error: File not found: {input_path}")
            return

        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        all_conversations = data.get("conversations", [])
        print(f"Loaded {len(all_conversations)} conversations from {input_path.name}")
        print(f"(media_posts: {len(data.get('media_posts', []))} — ignored)")

        if args.limit:
            all_conversations = all_conversations[:args.limit]
            print(f"\n[TEST MODE] Limited to {args.limit} conversations\n")

        # Filter already-processed
        if processed_ids:
            before = len(all_conversations)
            all_conversations = [
                c for c in all_conversations
                if c.get("conversation", {}).get("id", "") not in processed_ids
            ]
            skipped = before - len(all_conversations)
            if skipped:
                print(f"Skipping {skipped} already-processed conversations\n")

        total = len(all_conversations)
        print(f"\nTotal conversations to process: {total}\n")
        log.info(f"Total to process: {total}")

        async def _process_with_checkpoint(conv):
            await process_conversation(
                conv, client, col_knowledge, col_summaries, stats, increment_stat,
            )
            conv_id = conv.get("conversation", {}).get("id", "")
            if conv_id:
                async with stats_lock:
                    processed_ids.add(conv_id)

        for batch_start in range(0, total, BATCH_SIZE):
            batch     = all_conversations[batch_start:batch_start + BATCH_SIZE]
            batch_end = min(batch_start + BATCH_SIZE, total)
            print(f"\nBatch {batch_start+1}–{batch_end} of {total}")
            log.info(f"BATCH {batch_start+1}–{batch_end}")

            tasks = [_process_with_checkpoint(conv) for conv in batch]
            await asyncio.gather(*tasks)

            checkpoint_path.write_text(json.dumps(list(processed_ids)))
            log.info(f"CHECKPOINT: saved {len(processed_ids)} IDs after batch {batch_end}")

    # Final report
    print(f"\n{'─'*60}")
    print(f"✓ Complete")
    print(f"  Processed      : {stats['processed']}")
    print(f"  Noise filtered : {stats['noise_filtered']}")
    print(f"  Skipped        : {stats['skipped']}")
    print(f"  Knowledge      : {stats['knowledge']}")
    print(f"\n  knowledge total: {col_knowledge.count()}")
    print(f"\n  Log: {_log_path}")

    # Distance distribution
    if _all_dedup_distances:
        d = sorted(_all_dedup_distances)
        n = len(d)
        def pct(p): return d[int(n * p / 100)] if n > 0 else 0

        print(f"\n  ── Nearest-neighbour distance distribution ({n} exchanges) ──")
        print(f"  Min    : {d[0]:.4f}")
        print(f"  p10    : {pct(10):.4f}")
        print(f"  p25    : {pct(25):.4f}")
        print(f"  p50    : {pct(50):.4f}")
        print(f"  p75    : {pct(75):.4f}")
        print(f"  p90    : {pct(90):.4f}")
        print(f"  Max    : {d[-1]:.4f}")
        print(f"  Below 0.10: {sum(1 for x in d if x < 0.10)} ({sum(1 for x in d if x < 0.10)/n*100:.1f}%)")
        print(f"  Below 0.15: {sum(1 for x in d if x < 0.15)} ({sum(1 for x in d if x < 0.15)/n*100:.1f}%)")
        print(f"  Below 0.20: {sum(1 for x in d if x < 0.20)} ({sum(1 for x in d if x < 0.20)/n*100:.1f}%)")
        print(f"  Below 0.25: {sum(1 for x in d if x < 0.25)} ({sum(1 for x in d if x < 0.25)/n*100:.1f}%)")
        print(f"\n  Nothing was filtered — distances are informational only.")
        print(f"  Compare this distribution against the ChatGPT run to inform")
        print(f"  reclassify.py per-source dedup thresholds.")
        log.info(f"DISTANCE DISTRIBUTION: n={n} min={d[0]:.4f} p50={pct(50):.4f} max={d[-1]:.4f}")

    print(f"\nNOTE: facts and style collections are EMPTY until reclassify.py runs.")
    print(f"Next: reclassify.py → Admin → Rebuild Summaries")
    print(f"{'─'*60}\n")

    log.info(f"=== GROK INGEST COMPLETE === stats={stats}")


if __name__ == "__main__":
    asyncio.run(main())

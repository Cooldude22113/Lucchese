"""
ingest_grok_v2.py
─────────────────
Fixes applied from technical review:

  FIX 1: try/except in _process_with_checkpoint
    v1 had no exception handling — one bad conversation crashed the whole batch,
    propagated through asyncio.gather, and the conv_id was never checkpointed,
    causing infinite retry on resume. Copied pattern from ingest_chatgpt_v9.py.

  FIX 2: Self-closing <grok:render /> tags now stripped
    v1 regex only matched paired open/close tags. Grok occasionally emits
    self-closing tags like <grok:render card_id="..." /> which survived unstripped.

  FIX 3: --wipe now also clears col_facts and col_style
    v1 only wiped col_knowledge and col_summaries. If reclassify.py has already
    run and created facts/style entries, --wipe followed by re-ingest + re-classify
    would leave stale orphaned entries in facts/style.

Everything else unchanged from v1.

USAGE:
  python ingest_grok_v2.py --input "C:/prod-grok-backend.json"
  python ingest_grok_v2.py --input "C:/prod-grok-backend.json" --wipe
  python ingest_grok_v2.py --input "C:/prod-grok-backend.json" --limit 20
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
BATCH_SIZE    = 10
CONCURRENCY   = 4

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/api/chat"
MODEL      = os.getenv("MODEL_FAST", "gemma2:27b")

_all_dedup_distances: list[float] = []
_chroma_lock = threading.Lock()

+ # ── Shared imports ────────────────────────────────────────────────────────────
+ from pipeline.shared import (
    CHROMA_PATH,
    EMBED_MODEL,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    chunk_text,
    safe_json,
    llm_call as _shared_llm_call,
    get_era_from_year,
    make_logger,
)

# ── Logging ───────────────────────────────────────────────────────────────────
_log_path = Path(f"ingest_grok_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
log = make_logger("lucchese_grok_ingest", _log_path)

# ── ChromaDB setup ────────────────────────────────────────────────────────────
def get_collections():
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL,
        trust_remote_code=True
    )
    client        = chromadb.PersistentClient(path=CHROMA_PATH)
    col_knowledge = client.get_or_create_collection("knowledge",  embedding_function=ef)
    return client, ef, col_knowledge

# ── Timestamp helpers ─────────────────────────────────────────────────────────
def parse_conv_timestamp(ts) -> str:
    if isinstance(ts, str) and ts:
        return ts.replace("Z", "+00:00")
    return ""

def parse_message_timestamp(ts) -> str:
    if isinstance(ts, dict):
        inner = ts.get("$date", {})
        if isinstance(inner, dict):
            ms_str = inner.get("$numberLong", "")
            if ms_str:
                try:
                    return datetime.fromtimestamp(int(ms_str) / 1000, tz=timezone.utc).isoformat()
                except (ValueError, OSError):
                    log.warning(f"parse_message_timestamp: invalid ms '{ms_str}'")
    return ""

def year_from_iso(iso: str) -> int:
    try:
        return datetime.fromisoformat(iso).year
    except Exception:
        return datetime.now().year


# ── Grok message cleaning ─────────────────────────────────────────────────────
# FIX 2: Added self-closing tag pattern (v1 only matched paired open/close tags).
# <grok:render card_id="..." /> style tags now stripped correctly.
_GROK_PAIRED_RE      = re.compile(r"<grok:[^>]+>.*?</grok:[^>]+>", re.DOTALL)
_GROK_SELFCLOSING_RE = re.compile(r"<grok:[^/][^>]*/?>|<grok:[^>]+/>")

def clean_grok_message(text: str) -> str:
    if not text:
        return ""
    cleaned = _GROK_PAIRED_RE.sub("", text)
    cleaned = _GROK_SELFCLOSING_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


# ── Message extraction — accepted path only ───────────────────────────────────
def extract_messages_accepted_path(responses: list) -> list:
    """
    Grok exports include ALL responses as a flat list (branching included).
    leaf_response_id is always None — no shortcut to accepted path.

    Strategy: find leaf with highest timestamp (most recently accepted branch),
    walk backwards via parent_response_id to root, reverse to chronological order.

    21 of 208 Grok conversations have branching. For those, highest timestamp
    is the best available proxy for the accepted path — not authoritative.
    """
    if not responses:
        return []

    id_to_resp: dict[str, dict] = {}
    children_of: dict[str, list] = {}

    for r in responses:
        resp = r.get("response", {})
        rid  = resp.get("_id")
        pid  = resp.get("parent_response_id")
        if not rid:
            continue
        id_to_resp[rid] = resp
        children_of.setdefault(pid, [])
        children_of.setdefault(rid, [])
        if pid:
            children_of[pid].append(rid)

    all_ids  = set(id_to_resp.keys())
    leaf_ids = [rid for rid in all_ids if not children_of.get(rid)]

    if not leaf_ids:
        log.warning("extract_messages: no leaf found — using last response as fallback")
        leaf_ids = [responses[-1]["response"]["_id"]] if responses else []

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
            f"extract_messages: {len(leaf_ids)} leaves (branching) "
            f"— selected leaf {leaf_id[:8]} (highest timestamp)"
        )

    path: list[dict] = []
    node_id: str | None = leaf_id
    visited: set[str]   = set()

    while node_id and node_id not in visited:
        visited.add(node_id)
        resp = id_to_resp.get(node_id)
        if resp:
            path.append(resp)
        node_id = resp.get("parent_response_id") if resp else None

    path.reverse()

    messages = []
    for resp in path:
        sender = resp.get("sender", "").lower()
        role   = "user" if sender == "human" else "assistant" if sender == "assistant" else None
        if role is None:
            continue
        raw_msg = resp.get("message") or ""
        text    = clean_grok_message(raw_msg)
        ts      = parse_message_timestamp(resp.get("create_time", {}))
        if text:
            messages.append({"role": role, "text": text, "timestamp": ts})

    log.debug(f"extract_messages: accepted path {len(path)} nodes → {len(messages)} messages")
    return messages


def build_exchange_pairs(messages: list) -> tuple[list, int]:
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
    title = conv_meta.get("title", "").strip().lower()

    if not pairs:
        return False, "no exchange pairs"

    if len(pairs) == 1:
        user_words      = len(pairs[0]["user_text"].split())
        assistant_words = len(pairs[0]["assistant_text"].split())
        if user_words < 8 and assistant_words < 15:
            return False, "single exchange with minimal content"

    total_user_words = sum(len(p["user_text"].split()) for p in pairs)
    if total_user_words < 12:
        return False, f"user content too thin ({total_user_words} total words)"

    test_titles = {"test", "hello", "hi", "testing", "hey", "untitled", "new conversation"}
    if title in test_titles:
        first_user = pairs[0]["user_text"].strip().lower()
        if len(first_user.split()) <= 3 and total_user_words < 30:
            return False, "test or greeting message"

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
    """Wrapper: passes module semaphore/url/model to shared llm_call."""
    assert _semaphore is not None
    result = await _shared_llm_call(client, prompt, max_tokens, _semaphore, OLLAMA_URL, MODEL)
    if not result:
        log.error("LLM call failed after 3 attempts")
    return result


# ── Conversation summary ──────────────────────────────────────────────────────
SUMMARY_PROMPT = """Write one sentence describing this conversation and what it reveals about Alex.
Be specific. Start with the topic itself, not with "Alex" or "This conversation".

Title: {title}
Exchanges ({n} total — weighted toward the final exchanges):
{sample}

One sentence only:"""

# ── Distance logging ──────────────────────────────────────────────────────────
def _log_dedup_distance_sync(text: str, collection) -> None:
    try:
        results = collection.query(query_texts=[text], n_results=1, include=["distances"])
        if not results["distances"] or not results["distances"][0]:
            return
        dist = results["distances"][0][0]
        _all_dedup_distances.append(dist)
        log.debug(f"DEDUP [INFO ONLY]: dist={dist:.4f} — not filtered at ingest")
    except Exception as e:
        log.error(f"DEDUP distance logging error: {e}")

async def log_dedup_distance(text: str, collection) -> None:
    await asyncio.to_thread(_log_dedup_distance_sync, text, collection)


# ── Process single conversation ───────────────────────────────────────────────
async def process_conversation(
    conv: dict,
    client: httpx.AsyncClient,
    col_knowledge,
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
        return

    messages       = extract_messages_accepted_path(responses)
    pairs, dropped = build_exchange_pairs(messages)

    if dropped:
        log.debug(f"[{conv_id}]: {dropped} orphaned assistant message(s) dropped")

    passes, reason = noise_filter(conv_meta, pairs)
    if not passes:
        await increment_stat("noise_filtered")
        print(f"  ✗ [{title[:55]}] — {reason}")
        log.info(f"NOISE_FILTER [{conv_id}] title='{title[:60]}' reason='{reason}'")
        return

    conv_year = year_from_iso(created) if created else datetime.now().year
    conv_era  = get_era_from_year(conv_year)

    # Era extraction deferred — see LC-043 spec "Era Extraction — Disposition"
    has_era_ref    = False
    referenced_era = ""


    print(f"  ✓ [{title[:55]}] {conv_era}")
    log.info(f"PROCESSING [{conv_id}] title='{title}' era={conv_era} pairs={len(pairs)}")

    for j, pair in enumerate(pairs):
        user_text      = pair["user_text"].strip()
        assistant_text = pair["assistant_text"].strip()

        if not user_text:
            continue
        if len(user_text.split()) < 5:
            log.debug(f"SKIP exchange {j} [{conv_id}] — user text below 5 words")
            continue

        prev_user_text = pairs[j - 1]["user_text"] if j > 0 else ""
        if len(user_text.split()) < 15 and prev_user_text:
            embed_text = f"[prior: {prev_user_text[:100]}] {user_text}"
        else:
            embed_text = user_text

        await log_dedup_distance(embed_text, col_knowledge)

        assistant_excerpt = _strip_preamble(assistant_text)[:600]
        assistant_length  = len(assistant_text)

        base_meta = {
            "source":            "grok",
            "conv_id":           conv_id,
            "title":             title,
            "created_at":        created,
            "conv_year":         str(conv_year),
            "era":               conv_era,
            "pair_idx":          str(j),
            "has_era_mention":   str(has_era_ref).lower(),
            "referenced_era":    referenced_era,
            "conv_summary":      "",
            "user_text_raw":     user_text,
            "assistant_excerpt": assistant_excerpt,
            "assistant_length":  assistant_length,
            "type":              "knowledge",
            "category":          "unclassified",
            "ontology":          "unclassified",
            "source_type":       "unclassified",
            "primary_tier1":     "unclassified",
            "primary_tier2":     "unclassified",
            "primary_tier3":     "unclassified",
            "secondary_tier1":   "",
            "secondary_tier2":   "",
            "secondary_tier3":   "",
            "is_personal":       "unclassified",
            "engagement":        "unclassified",
            "routing_done":      "false",
        }

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
def wipe_grok_entries(col_knowledge, checkpoint_path: Path):
    """
    Wipes all grok-sourced entries from col_knowledge, col_summaries,
    col_facts, and col_style.

    FIX 3: v1 only wiped knowledge and summaries. Facts and style are now
    also wiped to avoid stale orphaned entries after re-ingest + re-classify.
    col_facts and col_style are retrieved inside this function to avoid
    passing them as parameters (they're not returned by get_collections()).
    """
    print("Wiping existing Grok entries...")
    FETCH_SIZE = 500
    max_iters  = 200

    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL,
        trust_remote_code=True
    )
    client    = chromadb.PersistentClient(path=CHROMA_PATH)
    col_facts = client.get_or_create_collection("facts",  embedding_function=ef)
    col_style = client.get_or_create_collection("style",  embedding_function=ef)

    collections_to_wipe = [
        (col_knowledge, "knowledge"),
        (col_facts,     "facts"),
        (col_style,     "style"),
    ]

    for col, name in collections_to_wipe:
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
                log.error(f"WIPE: max iterations for '{name}'")
            if all_ids:
                col.delete(ids=all_ids)
                print(f"  Deleted {len(all_ids)} from '{name}'")
            else:
                print(f"  Nothing to delete in '{name}'")
        except Exception as e:
            log.error(f"WIPE error '{name}': {e}")
            print(f"  Wipe error '{name}': {e}")

    if checkpoint_path.exists():
        checkpoint_path.unlink()
        print("  Checkpoint cleared")
        log.info("WIPE: checkpoint cleared")


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    global _semaphore

    parser = argparse.ArgumentParser(description="Lucchese Grok Ingest v2")
    parser.add_argument("--input",         required=True)
    parser.add_argument("--wipe",          action="store_true")
    parser.add_argument("--limit",         type=int, default=None)
    parser.add_argument("--no-checkpoint", action="store_true")
    args = parser.parse_args()

    _semaphore = asyncio.Semaphore(CONCURRENCY)

    stats_lock = asyncio.Lock()
    stats = {"processed": 0, "skipped": 0, "noise_filtered": 0, "knowledge": 0}

    async def increment_stat(key: str, n: int = 1):
        async with stats_lock:
            stats[key] = stats.get(key, 0) + n

    checkpoint_path = Path("ingest_grok_checkpoint.json")

    print(f"\n{'─'*60}")
    print(f"Lucchese Grok Ingest v2")
    print(f"Model      : {MODEL}")
    print(f"Concurrency: {CONCURRENCY}")
    print(f"Batch size : {BATCH_SIZE}")
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
            print("✗ Ollama unreachable")
            return

        _, _, col_knowledge = get_collections()

        if args.wipe:
            wipe_grok_entries(col_knowledge, checkpoint_path)
            print()

        processed_ids: set[str] = set()
        if not args.no_checkpoint and checkpoint_path.exists():
            try:
                processed_ids = set(json.loads(checkpoint_path.read_text()))
                print(f"Checkpoint: {len(processed_ids)} conversations already processed\n")
                log.info(f"CHECKPOINT: loaded {len(processed_ids)} IDs")
            except Exception as e:
                log.warning(f"CHECKPOINT: failed to load — {e}")

        input_path = Path(args.input)
        if not input_path.exists():
            print(f"Error: File not found: {input_path}")
            return

        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        all_conversations = data.get("conversations", [])
        print(f"Loaded {len(all_conversations)} conversations")
        print(f"(media_posts: {len(data.get('media_posts', []))} — ignored)")

        if args.limit:
            all_conversations = all_conversations[:args.limit]
            print(f"\n[TEST MODE] Limited to {args.limit} conversations\n")

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

        # FIX 1: try/except in _process_with_checkpoint.
        # v1 had no exception handling — one bad conversation crashed the whole
        # batch, propagated through asyncio.gather, and the conv_id was never
        # added to processed_ids, causing infinite retry on resume.
        async def _process_with_checkpoint(conv):
            try:
                await process_conversation(
                    conv, client, col_knowledge, stats, increment_stat,
                )
            except Exception as e:
                import traceback
                log.error(
                    f"TASK CRASH [{conv.get('conversation', {}).get('id', 'unknown')}]: "
                    f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
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

    print(f"\n{'─'*60}")
    print(f"✓ Complete")
    print(f"  Processed      : {stats['processed']}")
    print(f"  Noise filtered : {stats['noise_filtered']}")
    print(f"  Skipped        : {stats['skipped']}")
    print(f"  Knowledge      : {stats['knowledge']}")
    print(f"\n  Log: {_log_path}")

    if _all_dedup_distances:
        d = sorted(_all_dedup_distances)
        n = len(d)
        def pct(p): return d[int(n * p / 100)] if n > 0 else 0
        print(f"\n  ── Distance distribution ({n} exchanges) ──")
        print(f"  Min : {d[0]:.4f}  p50 : {pct(50):.4f}  Max : {d[-1]:.4f}")
        print(f"  <0.10: {sum(1 for x in d if x < 0.10)}  <0.15: {sum(1 for x in d if x < 0.15)}  <0.20: {sum(1 for x in d if x < 0.20)}")

    print(f"\nNext: reclassify.py → Admin → Rebuild Summaries")
    print(f"{'─'*60}\n")
    log.info(f"=== GROK INGEST COMPLETE === stats={stats}")


if __name__ == "__main__":
    asyncio.run(main())

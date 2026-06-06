"""
ingest_chatgpt_v8.py
────────────────────
Lean, honest ingestion of ChatGPT exports into ChromaDB for Lucchese.

CHANGES FROM v8 (based on log analysis and further audit):

  CONTEXT SEED BUG FIXED:
    v7 stored embed_text (with [prior: ...] prefix) as the ChromaDB document.
    v8 stores embed_text as document (so ChromaDB embeds it correctly) but also
    stores clean user_text in metadata as user_text_raw. Serving layer must read
    user_text_raw from metadata, not the document field.

  ASSISTANT_TEXT METADATA FIXED:
    v7 stored up to 4000 chars of assistant_text per chunk — caused storage bloat
    (4000 chars × many chunks × many pairs = significant). v8 stores:
    - assistant_excerpt: 600 chars, preamble-stripped (enough for context)
    - assistant_length: int char count of full response (for reference)

  DEDUP THRESHOLD CALIBRATION:
    v7 used DEDUP_THRESHOLD=0.25 which the log proved was wrong — it was
    deduplicating ~80% of a 17-pair conversation as "duplicates". Log showed
    distances clustering 0.09-0.24 for genuinely distinct content.
    v8 ships with DEDUP_CALIBRATION_MODE=True (threshold disabled).
    Run calibration mode first, read the distribution summary printed at end,
    find where genuine duplicates cluster (likely 0.08-0.12), set threshold,
    set DEDUP_CALIBRATION_MODE=False, rerun.

WORKFLOW:
    1. Run with --limit 100 — read distance distribution at end
    2. Manually sample pairs at each distance band to find duplicate cluster
    3. Set per-domain thresholds in reclassify.py based on distribution
    4. Run full ingest with --wipe
    5. reclassify.py → Admin → Rebuild Summaries

SERVING LAYER NOTE:
    Documents in col_knowledge may contain [prior: ...] prefix for short messages.
    Always read user_text_raw from metadata for clean display.
    assistant_excerpt in metadata is 600 chars, preamble-stripped.
"""

import json
import argparse
import glob
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

+ # ── Config ────────────────────────────────────────────────────────────────────
+ # Constants are defined in pipeline/shared.py and imported below.
+ # Local overrides: set these here if this script needs different values.
BATCH_SIZE  = 10
CONCURRENCY = 4

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/api/chat"
MODEL      = os.getenv("MODEL_FAST", "gemma2:27b")

# ── Dedup note ────────────────────────────────────────────────────────────────
# Dedup is NOT performed at ingest time.
# Global nearest-neighbour dedup before taxonomy classification produces false
# positives — content gets skipped because it's close to something in a different
# domain, not because it's actually a duplicate.
# Dedup is deferred to reclassify.py where taxonomy is known and within-domain
# comparison is possible. Distance logging still runs at ingest for calibration.
# _all_dedup_distances collects distances for the distribution summary at run end.

# Tracks all distances seen during run for distribution summary at end.
# Used in both calibration and normal mode.
_all_dedup_distances: list[float] = []

# threading.Lock for all ChromaDB mutations.
# asyncio.Lock is NOT thread-safe from asyncio.to_thread pool.
# One lock for all collections — conservative but correct at CONCURRENCY=4.
_chroma_lock = threading.Lock()

+ # ── Shared imports ────────────────────────────────────────────────────────────
from pipeline.shared import (
    CHROMA_PATH,
    EMBED_MODEL,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    chunk_text,
    safe_json,
    llm_call as _shared_llm_call,
    ERA_BOUNDARIES,
    get_era_from_year,
    TEMPORAL_SIGNALS,
    ERA_PROMPT,
    extract_era_mention as _shared_extract_era,
    make_logger,
    sample_pairs_for_summary,
)

# ── Logging ───────────────────────────────────────────────────────────────────
_log_path = Path(f"ingest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
log = make_logger("lucchese_ingest", _log_path)


# ── ChromaDB setup ────────────────────────────────────────────────────────────
def get_collections():
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL,
        trust_remote_code=True  # required by nomic-embed-text-v1
    )
    client        = chromadb.PersistentClient(path=CHROMA_PATH)
    col_knowledge = client.get_or_create_collection("knowledge",  embedding_function=ef)
    # facts, style, and summaries are NOT written at ingest time
    return client, ef, col_knowledge


# ── Timestamp helpers ─────────────────────────────────────────────────────────
def parse_timestamp(ts) -> str:
    if isinstance(ts, (int, float)) and ts > 0:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return ""

def year_from_iso(iso: str) -> int:
    try:
        return datetime.fromisoformat(iso).year
    except Exception:
        return datetime.now().year


# ── Message extraction — accepted path only ───────────────────────────────────
def extract_messages_accepted_path(mapping: dict, current_node: str | None) -> list:
    """
    Walk BACKWARDS from current_node to root following parent links.
    This gives only the accepted conversation path — not regenerated branches.

    Previous BFS traversed all children, producing 3-4 versions of the same
    exchange when Alex hit "regenerate". Estimated 20-40% of previous database
    was regenerated response variants.

    Handles two export formats:
    - Modern ChatGPT exports: parent field
    - Older/API exports: parent_id field
    Falls back to BFS if current_node unavailable, with explicit logging of why.
    """
    if current_node and current_node in mapping:
        path    = []
        node_id = current_node
        visited = set()
        used_parent_id = False

        while node_id and node_id not in visited:
            visited.add(node_id)
            path.append(node_id)
            node = mapping.get(node_id, {})
            # Handle both modern (parent) and older (parent_id) export formats
            parent = node.get("parent") or node.get("parent_id")
            if node.get("parent_id") and not node.get("parent"):
                used_parent_id = True
            node_id = parent

        path.reverse()

        messages = []
        for nid in path:
            node = mapping.get(nid, {})
            msg  = node.get("message")
            if not msg:
                continue
            role  = msg.get("author", {}).get("role", "")
            parts = msg.get("content", {}).get("parts", [])
            text  = " ".join([p for p in parts if isinstance(p, str)]).strip()
            ts    = parse_timestamp(msg.get("create_time"))
            if text and role in ("user", "assistant"):
                messages.append({"role": role, "text": text, "timestamp": ts})

        if messages:
            fmt = "parent_id (older format)" if used_parent_id else "parent"
            log.debug(f"extract_messages: used accepted path ({len(path)} nodes, field={fmt})")
            return messages
        else:
            log.warning(
                f"extract_messages: accepted path produced no messages "
                f"(current_node={current_node}, path_len={len(path)}) — falling back to BFS"
            )

    # Fallback: BFS (used when current_node unavailable or path produces no messages)
    fallback_reason = "current_node not in mapping" if not (current_node and current_node in mapping) else "accepted path empty"
    log.warning(f"extract_messages: BFS fallback triggered — reason: {fallback_reason}. "
                f"This conversation will include all regenerated response branches.")

    root = None
    for node_id, node in mapping.items():
        parent = node.get("parent") or node.get("parent_id")
        if parent is None:
            root = node_id
            break
    if not root:
        return []

    messages = []
    visited  = set()
    queue    = deque([root])

    while queue:
        node_id = queue.popleft()
        if node_id in visited:
            continue
        visited.add(node_id)
        node = mapping.get(node_id, {})
        msg  = node.get("message")
        if msg:
            role  = msg.get("author", {}).get("role", "")
            parts = msg.get("content", {}).get("parts", [])
            text  = " ".join([p for p in parts if isinstance(p, str)]).strip()
            ts    = parse_timestamp(msg.get("create_time"))
            if text and role in ("user", "assistant"):
                messages.append({"role": role, "text": text, "timestamp": ts})
        queue.extend(node.get("children", []))

    return messages


def build_exchange_pairs(messages: list) -> tuple[list, int]:
    """Returns (pairs, dropped_count). Logs orphaned assistant messages."""
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


# ── Preamble stripper (module level — not inside loop) ────────────────────────
def _strip_preamble(text: str, min_words: int = 12) -> str:
    """
    Strip short preamble sentences from assistant responses.
    e.g. "Great question! Let me explain." → skipped, substance starts after.
    Falls back to original text if all sentences are short.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    for i, s in enumerate(sentences):
        if len(s.split()) >= min_words:
            return " ".join(sentences[i:])
    return text


# ── Deterministic noise filter — no LLM ──────────────────────────────────────
# Replaces the LLM quality gate entirely for most cases.
# Goal: discard literal garbage only. Everything ambiguous passes.
# The cost of storing a marginally irrelevant conversation is trivial.
# The cost of discarding an irreplaceable snapshot of Alex's thinking is permanent.

_ARTEFACT_PATTERNS = [
    r'\bgenerate\b.{0,20}\bimage\b',
    r'\bmake.{0,20}(less blurry|clearer|sharper)\b',
    r'\bcreate\b.{0,20}\b(logo|banner|thumbnail|image)\b',
    r'\bdraw\b.{0,30}\b(picture|image|illustration)\b',
]

def noise_filter(conv: dict, pairs: list) -> tuple[bool, str]:
    """
    Returns (passes, reason). No LLM calls — deterministic only.
    Fails closed only on clear garbage. Everything uncertain passes.
    """
    title = conv.get("title", "").strip().lower()

    if not pairs:
        return False, "no exchange pairs"

    # Single exchange, minimal content on both sides
    if len(pairs) == 1:
        user_words      = len(pairs[0]["user_text"].split())
        assistant_words = len(pairs[0]["assistant_text"].split())
        if user_words < 8 and assistant_words < 15:
            return False, "single exchange with minimal content"

    # Total user word count across all pairs — checked BEFORE title filter.
    # Total word count has veto power: a conversation with 30+ substantive
    # exchanges should never be filtered just because of a default title.
    total_user_words = sum(len(p["user_text"].split()) for p in pairs)
    if total_user_words < 12:
        return False, f"user content too thin ({total_user_words} total words)"

    # Test/hello messages — only filter if title is default AND content is thin.
    # "new conversation" is ChatGPT's default title for many real conversations
    # Alex never renamed. Check title AFTER total word count so substantive
    # conversations are never dropped just because of an unrenamed title.
    test_titles = {"test", "hello", "hi", "testing", "hey", "untitled", "new conversation"}
    if title in test_titles:
        first_user = pairs[0]["user_text"].strip().lower()
        if len(first_user.split()) <= 3 and total_user_words < 30:
            return False, "test or greeting message"

    # Pure image generation — every user message matches artefact pattern
    non_empty_pairs = [p for p in pairs if p["user_text"].strip()]
    if non_empty_pairs and all(
        any(re.search(pat, p["user_text"].lower()) for pat in _ARTEFACT_PATTERNS)
        for p in non_empty_pairs
    ):
        return False, "pure image/artefact generation conversation"

    return True, "passes noise filter"


# ── LLM call (with retry) ─────────────────────────────────────────────────────
_semaphore: asyncio.Semaphore | None = None

async def llm_call(client: httpx.AsyncClient, prompt: str, max_tokens: int = 100) -> str:
    """Wrapper: passes module semaphore/url/model to shared llm_call."""
    assert _semaphore is not None, "semaphore not initialised"
    result = await _shared_llm_call(client, prompt, max_tokens, _semaphore, OLLAMA_URL, MODEL)
    if not result:
        log.error("LLM call failed after 3 attempts")
    return result

# ── Conversation summary ──────────────────────────────────────────────────────
SUMMARY_PROMPT = """Write one sentence describing this conversation and what it reveals about Alex.
Be specific. Start with the topic itself, not with "Alex" or "This conversation".

Good example: "Property deal analysis for a two-bed flat in Manchester exploring
yield vs capital growth, showing Alex stress-testing numbers before committing."

Title: {title}
Exchanges ({n} total — weighted toward the final exchanges where positions develop):
{sample}

One sentence only:"""


# ── Dedup — distance logging only ────────────────────────────────────────────
# Dedup is NOT performed at ingest time. Reason: global nearest-neighbour dedup
# is wrong before taxonomy classification. A distance of 0.08 against a topically
# unrelated stored item doesn't mean the new exchange is a duplicate — it means
# it happened to be the closest thing globally across all domains.
#
# Correct dedup = within-domain, after taxonomy classification.
# That happens in reclassify.py, not here.
#
# What this function DOES: logs distance for calibration purposes only.
# The distribution data helps reclassify.py set a per-domain threshold.
# Returns False always — never skips content at ingest time.
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
    stats: dict,
    increment_stat,
) -> None:

    conv_id      = conv.get("id") or conv.get("conversation_id", str(uuid.uuid4()))
    title        = conv.get("title", "Untitled")
    created      = parse_timestamp(conv.get("create_time"))
    mapping      = conv.get("mapping", {})
    current_node = conv.get("current_node")  # accepted path endpoint

    if not mapping:
        await increment_stat("skipped")
        log.debug(f"SKIP [{conv_id}]: no mapping")
        return

    messages       = extract_messages_accepted_path(mapping, current_node)
    pairs, dropped = build_exchange_pairs(messages)

    if dropped:
        log.debug(f"[{conv_id}]: {dropped} orphaned assistant message(s) dropped")

    # ── Deterministic noise filter ────────────────────────────────────────────
    passes, reason = noise_filter(conv, pairs)
    if not passes:
        await increment_stat("noise_filtered")
        print(f"  ✗ [{title[:55]}] — {reason}")
        log.info(f"NOISE_FILTER [{conv_id}] title='{title[:60]}' reason='{reason}'")
        return

    # ── Conversation-level metadata ───────────────────────────────────────────
    conv_year = year_from_iso(created) if created else datetime.now().year
    conv_era  = get_era_from_year(conv_year)

    # Era extraction deferred — see LC-043 spec "Era Extraction — Disposition"
    # has_era_mention and referenced_era ship as "unclassified" until a dedicated
    # stage is specified. extract_era_mention is preserved in pipeline/shared.py.
    has_era_ref    = False
    referenced_era = ""

    print(f"  ✓ [{title[:55]}] {conv_era}")
    log.info(f"PROCESSING [{conv_id}] title='{title}' era={conv_era} pairs={len(pairs)}")

    # ── Process each exchange pair ────────────────────────────────────────────
    for j, pair in enumerate(pairs):
        user_text      = pair["user_text"].strip()
        assistant_text = pair["assistant_text"].strip()

        if not user_text:
            continue

        # Deterministic content floor — skip noise without LLM call
        if len(user_text.split()) < 5:
            log.debug(f"SKIP exchange {j} [{conv_id}] — user text below 5 words")
            continue

        # ── Context seed for short messages ──────────────────────────────────
        # Short messages are often context-dependent: "What about the dosage?"
        # embed_text = what gets embedded (may contain [prior: ...] prefix)
        # user_text  = what gets stored as document (clean, no prefix)
        # The serving layer should read user_text_raw from metadata, not the document field.
        # This separation means embeddings capture context; stored content stays clean.
        prev_user_text = pairs[j - 1]["user_text"] if j > 0 else ""
        if len(user_text.split()) < 15 and prev_user_text:
            embed_text = f"[prior: {prev_user_text[:100]}] {user_text}"
        else:
            embed_text = user_text

        # ── Log distance for calibration (no filtering at ingest) ────────────
        # Dedup filtering happens in reclassify.py after taxonomy is known.
        # Distance is logged here to inform reclassify.py threshold setting.
        #await log_dedup_distance(embed_text, col_knowledge)

        # ── Assistant excerpt ─────────────────────────────────────────────────
        assistant_excerpt = _strip_preamble(assistant_text)[:600]
        assistant_length  = len(assistant_text)

        # ── Build metadata ────────────────────────────────────────────────────
        base_meta = {
            "source":             "chatgpt",
            "conv_id":            conv_id,
            "title":              title,
            "created_at":         created,
            "conv_year":          str(conv_year),
            "era":                conv_era,
            "pair_idx":           str(j),
            "has_era_mention":    str(has_era_ref).lower(),
            "referenced_era":     referenced_era,
            "conv_summary":       "",
            "user_text_raw":      user_text,          # clean user text — serving layer reads this
            "assistant_excerpt":  assistant_excerpt,   # preamble-stripped, 600 chars
            "assistant_length":   assistant_length,    # full response length for reference
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

        # ── Chunk and store ───────────────────────────────────────────────────
        # Documents stored = embed_text chunks (may contain [prior: ...] prefix).
        # Embeddings computed from embed_text — this is intentional.
        # Serving layer must read user_text_raw from metadata for clean display.
        for k, chunk in enumerate(chunk_text(embed_text)):
            chunk_meta = {**base_meta, "chunk_idx": str(k)}

            def _upsert_knowledge(meta=chunk_meta, doc=chunk, k=k):
                with _chroma_lock:
                    col_knowledge.upsert(
                        ids       = [f"cgpt_know_{conv_id}_{j}_{k}"],
                        documents = [doc],
                        metadatas = [meta],
                    )

            await asyncio.to_thread(_upsert_knowledge)
            await increment_stat("knowledge")

    await increment_stat("processed")


# ── Wipe ──────────────────────────────────────────────────────────────────────
def wipe_chatgpt_entries(col_knowledge, checkpoint_path: Path):
    """
    Wipes all chatgpt-sourced entries from ChromaDB.
    Summaries are now managed by generate_summaries.py -- not wiped here.
    Also clears checkpoint file ...
    causing all conversations to be skipped on the next run (empty database bug).
    """
    print("Wiping existing ChatGPT entries...")
    FETCH_SIZE   = 500
    max_iters    = 200  # guard against infinite loop on buggy ChromaDB versions

    for col in [col_knowledge]:
        try:
            all_ids = []
            offset  = 0
            iters   = 0
            while iters < max_iters:
                results = col.get(
                    where   = {"source": "chatgpt"},
                    limit   = FETCH_SIZE,
                    offset  = offset,
                    # Note: do NOT pass include=["ids"] — ids are always returned
                    # and "ids" is not a valid include value in ChromaDB >= 0.4.x.
                    # Passing it raises a validation error that is silently caught,
                    # causing wipe to appear to succeed while doing nothing.
                )
                if not results["ids"]:
                    break
                all_ids.extend(results["ids"])
                offset += FETCH_SIZE
                iters  += 1
            if iters >= max_iters:
                log.error(f"WIPE: max iterations reached for '{col.name}' — possible ChromaDB bug")

            if all_ids:
                col.delete(ids=all_ids)
                print(f"  Deleted {len(all_ids)} from '{col.name}'")
            else:
                print(f"  Nothing to delete in '{col.name}'")
        except Exception as e:
            log.error(f"WIPE error '{col.name}': {e}")
            print(f"  Wipe error '{col.name}': {e}")

    # Clear checkpoint — critical, previous versions left this intact
    if checkpoint_path.exists():
        checkpoint_path.unlink()
        print("  Checkpoint cleared")
        log.info("WIPE: checkpoint file cleared")


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    global _semaphore

    parser = argparse.ArgumentParser(description="Lucchese ChatGPT Ingest v9")
    parser.add_argument("--input",         required=True, nargs="+")
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

    input_files = []
    for pattern in args.input:
        expanded = glob.glob(pattern)
        input_files.extend(expanded if expanded else [pattern])
    input_files = sorted(set(input_files))

    checkpoint_path = Path("ingest_checkpoint.json")

    print(f"\n{'─'*60}")
    print(f"Lucchese ChatGPT Ingest v9")
    print(f"Model      : {MODEL}")
    print(f"Concurrency: {CONCURRENCY}")
    print(f"Batch size : {BATCH_SIZE}")
    print(f"Embeds     : user_text only (assistant stored as metadata)")
    print(f"Gate       : deterministic code only (no LLM gate)")
    print(f"Routing    : deferred to reclassify.py")
    print(f"Files      : {', '.join(input_files)}")
    print(f"Log        : {_log_path}")
    print(f"{'─'*60}\n")

    log.info(f"=== INGEST RUN START === model={MODEL} files={input_files}")

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
            # Wipe clears checkpoint too — critical fix
            wipe_chatgpt_entries(col_knowledge, checkpoint_path)
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

        # Load all conversations
        all_conversations = []
        for path in input_files:
            p = Path(path)
            if not p.exists():
                print(f"Not found: {path}")
                log.warning(f"File not found: {path}")
                continue
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                all_conversations.extend(data)
                print(f"Loaded {len(data)} conversations from {p.name}")
            else:
                log.warning(f"Unexpected format in {p.name} — expected list")

        if args.limit:
            all_conversations = all_conversations[:args.limit]
            print(f"\n[TEST MODE] Limited to {args.limit} conversations\n")

        # Filter already-processed
        if processed_ids:
            before             = len(all_conversations)
            all_conversations  = [
                c for c in all_conversations
                if (c.get("id") or c.get("conversation_id", "")) not in processed_ids
            ]
            skipped_count = before - len(all_conversations)
            if skipped_count:
                print(f"Skipping {skipped_count} already-processed conversations\n")

        total = len(all_conversations)
        print(f"\nTotal conversations to process: {total}\n")
        log.info(f"Total to process: {total}")

        async def _process_with_checkpoint(conv):
            try:
                await process_conversation(
                    conv, client, col_knowledge, stats, increment_stat,
                )
            except Exception as e:
                import traceback
                log.error(f"TASK CRASH: {type(e).__name__}: {e}\n{traceback.format_exc()}")
            conv_id = conv.get("id") or conv.get("conversation_id", "")
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

            # Write checkpoint at batch boundary only — not per-conversation
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

    # ── Distance distribution summary ─────────────────────────────────────────
    # Ingest does NOT filter on these distances — dedup is deferred to reclassify.py.
    # This distribution informs reclassify.py's per-domain threshold setting.
    # After reviewing this, manually sample pairs at each distance band to verify
    # where genuine duplicates actually cluster vs. distinct-but-related content.
    if _all_dedup_distances:
        import statistics
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
        print(f"\n  Nothing was filtered — these distances are informational only.")
        print(f"  Use this distribution in reclassify.py to set per-domain dedup thresholds.")
        print(f"  Manually sample pairs at 0.05-0.10, 0.10-0.15, 0.15-0.20 bands")
        print(f"  to verify where genuine duplicates end and distinct content begins.")

        log.info(f"DISTANCE DISTRIBUTION: n={n} min={d[0]:.4f} p25={pct(25):.4f} p50={pct(50):.4f} p75={pct(75):.4f} max={d[-1]:.4f}")

    print(f"\nNOTE: facts and style collections are EMPTY until reclassify.py runs.")
    print(f"Next: reclassify.py → Admin → Rebuild Summaries")
    print(f"{'─'*60}\n")

    log.info(f"=== INGEST RUN COMPLETE === stats={stats}")


if __name__ == "__main__":
    asyncio.run(main())

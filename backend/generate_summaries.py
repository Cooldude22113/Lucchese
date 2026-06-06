"""
pipeline/generate_summaries.py
───────────────────────────────
Stage 3: Generate conversation summaries from classified exchange records.

Reads classified entries from col_knowledge (routing_done="true"),
groups by conv_id, generates one summary per conversation via LLM,
writes to col_summaries.

Invocation:
  python generate_summaries.py
  python generate_summaries.py --source chatgpt
  python generate_summaries.py --source grok
  python generate_summaries.py --limit 20
  python generate_summaries.py --wipe       # clears col_summaries before regenerating

Upsert semantics: safe to re-run. Summaries for conversations with updated
classifications will be overwritten.

Does NOT run for conversations where all entries have routing_done="false".
Those must go through classify + write before summaries can be generated.

Summary ID format: summary_{conv_id} (replaces conv_summary_ and grok_summary_ prefixes).
Old IDs from previous ingest-time summary runs are left in place — they are
inert until a wipe+regenerate cycle. See PIPELINE.md for wipe procedure.
"""

import argparse
import asyncio
import os
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import chromadb
import httpx
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
load_dotenv()

from pipeline.shared import (
    sample_pairs_for_summary,
    llm_call,
    make_logger,
)

CHROMA_PATH  = os.getenv("CHROMA_PATH", "./chroma_db")
EMBED_MODEL  = "nomic-ai/nomic-embed-text-v1"
CONCURRENCY  = 4

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/api/chat"
MODEL      = os.getenv("MODEL_FAST", "gemma2:27b")

_log_path = Path(f"generate_summaries_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
log = make_logger("lucchese_summaries", _log_path)

_chroma_lock = threading.Lock()
_semaphore: asyncio.Semaphore | None = None

# ── Summary prompt ────────────────────────────────────────────────────────────
# Stage-specific — kept local, not in shared.py.
# Input is user_text_raw strings only (not raw pair dicts with assistant text).
# Summary characterises Alex's contribution specifically.
SUMMARY_PROMPT = """Write one sentence describing this conversation and what it reveals about Alex.
Be specific. Start with the topic itself, not with "Alex" or "This conversation".

Good example: "Property deal analysis for a two-bed flat in Manchester exploring
yield vs capital growth, showing Alex stress-testing numbers before committing."

Title: {title}
Exchanges ({n} total — weighted toward the final exchanges where positions develop):
{sample}

One sentence only:"""


def get_collections():
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL,
        trust_remote_code=True,
    )
    client        = chromadb.PersistentClient(path=CHROMA_PATH)
    col_knowledge = client.get_or_create_collection("knowledge",  embedding_function=ef)
    col_summaries = client.get_or_create_collection("summaries",  embedding_function=ef)
    return client, col_knowledge, col_summaries


def wipe_summaries(col_summaries, source: str | None = None):
    """Delete all entries from col_summaries, optionally filtered by source."""
    print(f"Wiping summaries{' (source: ' + source + ')' if source else ''}...")
    FETCH_SIZE = 500
    all_ids    = []
    offset     = 0

    while True:
        kw = {"limit": FETCH_SIZE, "offset": offset}
        if source:
            kw["where"] = {"source": source}
        try:
            r = col_summaries.get(**kw)
        except Exception as e:
            log.error(f"WIPE fetch error at offset {offset}: {e}")
            break
        if not r["ids"]:
            break
        all_ids.extend(r["ids"])
        offset += FETCH_SIZE

    if all_ids:
        with _chroma_lock:
            col_summaries.delete(ids=all_ids)
        print(f"  Deleted {len(all_ids)} summaries")
    else:
        print("  Nothing to delete")
    log.info(f"WIPE: deleted {len(all_ids)} summary entries")


async def generate_summary_for_conv(
    client: httpx.AsyncClient,
    conv_id: str,
    title: str,
    source: str,
    primary_tier1: str,
    era: str,
    entries: list[dict],
    col_summaries,
) -> bool:
    """
    Generate and upsert one summary for a conversation.
    entries: list of metadata dicts from col_knowledge, sorted by pair_idx.
    Returns True on success, False on failure.
    """
    assert _semaphore is not None

    # Build pairs list from user_text_raw values
    pairs = [{"user_text": e.get("user_text_raw", "")} for e in entries]
    sampled = sample_pairs_for_summary(pairs)

    # Format sample as [Alex]: lines only (no assistant text)
    sample_text = "\n".join(
        f"[Alex]: {p['user_text'][:200]}"
        for p in sampled
        if p["user_text"].strip()
    )

    if not sample_text:
        log.warning(f"SUMMARY_FAIL [{conv_id}]: no user_text_raw content in entries")
        return False

    prompt = SUMMARY_PROMPT.format(
        title=title,
        n=len(pairs),
        sample=sample_text,
    )

    try:
        summary = await llm_call(client, prompt, 80, _semaphore, OLLAMA_URL, MODEL)
        summary = summary.strip()
    except Exception as e:
        log.error(f"SUMMARY_FAIL [{conv_id}]: LLM error — {e}")
        return False

    if not summary:
        log.warning(f"SUMMARY_FAIL [{conv_id}]: LLM returned empty response")
        return False

    metadata = {
        "source":        source,
        "conv_id":       conv_id,
        "title":         title,
        "type":          "conv_summary",
        "primary_tier1": primary_tier1,
        "era":           era,
        "generated_at":  datetime.now(timezone.utc).isoformat(),
    }

    def _upsert():
        with _chroma_lock:
            col_summaries.upsert(
                ids       = [f"summary_{conv_id}"],
                documents = [summary],
                metadatas = [metadata],
            )

    await asyncio.to_thread(_upsert)
    log.info(f"SUMMARY [{conv_id}]: {summary[:80]}")
    return True


async def main():
    global _semaphore

    parser = argparse.ArgumentParser(description="Lucchese generate_summaries")
    parser.add_argument("--source", type=str, default=None, help="chatgpt or grok")
    parser.add_argument("--limit",  type=int, default=None, help="Limit conversations processed")
    parser.add_argument("--wipe",   action="store_true",    help="Clear col_summaries before generating")
    args = parser.parse_args()

    _semaphore = asyncio.Semaphore(CONCURRENCY)

    print(f"\n{'─'*60}")
    print(f"Lucchese generate_summaries")
    print(f"Model       : {MODEL}")
    print(f"Concurrency : {CONCURRENCY}")
    if args.source: print(f"Source      : {args.source} only")
    if args.limit:  print(f"Limit       : {args.limit} conversations [TEST MODE]")
    if args.wipe:   print(f"Mode        : WIPE then regenerate")
    print(f"Log         : {_log_path}")
    print(f"{'─'*60}\n")

    log.info(f"=== SUMMARIES START === model={MODEL} source={args.source} limit={args.limit} wipe={args.wipe}")

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    _, col_knowledge, col_summaries = get_collections()

    if args.wipe:
        wipe_summaries(col_summaries, source=args.source)
        print()

    # Fetch all classified entries from col_knowledge
    print("Fetching classified entries...")
    where_clause = {"routing_done": {"$eq": "true"}}
    if args.source:
        where_clause = {"$and": [
            {"routing_done": {"$eq": "true"}},
            {"source": {"$eq": args.source}},
        ]}

    all_ids, all_metas, offset = [], [], 0
    while True:
        try:
            b = col_knowledge.get(
                where   = where_clause,
                limit   = 500,
                offset  = offset,
                include = ["metadatas"],
            )
        except Exception as e:
            log.error(f"Fetch error at offset {offset}: {e}")
            print(f"  Fetch error: {e}")
            break
        if not b["ids"]:
            break
        all_ids.extend(b["ids"])
        all_metas.extend(b["metadatas"])
        offset += 500
        print(f"  Fetched {len(all_ids)} entries...", end="\r")

    print(f"\nClassified entries fetched: {len(all_ids)}")

    if not all_ids:
        print("\nNo classified entries found. Run reclassify.py + write_classifications.py first.")
        return

    # Group by conv_id, sort by pair_idx within each group
    by_conv: dict[str, list[dict]] = defaultdict(list)
    for meta in all_metas:
        conv_id = meta.get("conv_id", "")
        if conv_id:
            by_conv[conv_id].append(meta)

    for conv_id in by_conv:
        by_conv[conv_id].sort(
            key=lambda m: int(m.get("pair_idx", 0)) if str(m.get("pair_idx", "0")).isdigit() else 0
        )

    conv_ids = list(by_conv.keys())
    if args.limit:
        conv_ids = conv_ids[:args.limit]
        print(f"[TEST MODE] Limited to {args.limit} conversations\n")

    total = len(conv_ids)
    print(f"\nGenerating summaries for {total} conversations...\n")
    log.info(f"Processing {total} conversations")

    stats = {"generated": 0, "failed": 0}

    async with httpx.AsyncClient() as client:
        try:
            await client.get(base_url, timeout=5)
            print("✓ Ollama reachable\n")
        except Exception:
            print("✗ Ollama unreachable — is it running?")
            log.error(f"Ollama unreachable at {base_url}")
            return

        # Process in batches of CONCURRENCY
        for batch_start in range(0, total, CONCURRENCY):
            batch_conv_ids = conv_ids[batch_start:batch_start + CONCURRENCY]

            tasks = []
            for conv_id in batch_conv_ids:
                entries       = by_conv[conv_id]
                # Use metadata from representative (first sorted) entry
                rep_meta      = entries[0]
                title         = rep_meta.get("title", "Untitled")
                source        = rep_meta.get("source", "")
                primary_tier1 = rep_meta.get("primary_tier1", "")
                era           = rep_meta.get("era", "")

                tasks.append(generate_summary_for_conv(
                    client, conv_id, title, source, primary_tier1, era,
                    entries, col_summaries,
                ))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for conv_id, result in zip(batch_conv_ids, results):
                if isinstance(result, Exception):
                    log.error(f"SUMMARY_FAIL [{conv_id}]: {result}")
                    stats["failed"] += 1
                elif result:
                    stats["generated"] += 1
                else:
                    stats["failed"] += 1

            done = min(batch_start + CONCURRENCY, total)
            print(f"  {done}/{total} | generated={stats['generated']} failed={stats['failed']}")

    print(f"\n{'─'*60}")
    print(f"✓ SUMMARY COMPLETE: generated={stats['generated']} failed={stats['failed']}")
    print(f"  Log: {_log_path}")
    print(f"{'─'*60}\n")
    log.info(f"=== SUMMARY COMPLETE: generated={stats['generated']} failed={stats['failed']} ===")


if __name__ == "__main__":
    asyncio.run(main())

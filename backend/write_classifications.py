"""
pipeline/write_classifications.py
──────────────────────────────────
Stage 2: Read classifications JSONL and commit to ChromaDB.

Invocation:
  python write_classifications.py --input classifications_<timestamp>.jsonl
  python write_classifications.py --input classifications_<timestamp>.jsonl --dry-run
  python write_classifications.py --input classifications_<timestamp>.jsonl --source chatgpt

--dry-run: validates all records, prints what would be written, makes no Chroma writes.

Idempotent: upsert semantics throughout. Running twice on the same JSONL
produces the same Chroma state.

Does NOT call any LLM.
"""

import argparse
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
load_dotenv()

from pipeline.shared import (
    VALID_TIER1,
    validate_tier,
    make_logger,
)

CHROMA_PATH  = os.getenv("CHROMA_PATH", "./chroma_db")
EMBED_MODEL  = "nomic-ai/nomic-embed-text-v1"
MIN_FACT_LEN  = 50
MIN_STYLE_LEN = 100

_log_path = Path(f"write_classifications_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
log = make_logger("lucchese_write", _log_path)

_chroma_lock = threading.Lock()

REQUIRED_FIELDS = {"conv_id", "pair_idx", "all_chunk_ids", "user_text_raw", "classification", "route_facts", "route_style"}


def get_collections():
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL,
        trust_remote_code=True,
    )
    client        = chromadb.PersistentClient(path=CHROMA_PATH)
    col_knowledge = client.get_or_create_collection("knowledge", embedding_function=ef)
    col_facts     = client.get_or_create_collection("facts",     embedding_function=ef)
    col_style     = client.get_or_create_collection("style",     embedding_function=ef)
    return client, col_knowledge, col_facts, col_style


def validate_record(record: dict, line_number: int) -> tuple[bool, str]:
    """
    Validate a single JSONL record. Returns (valid, reason).
    Invalid records are logged and skipped — not an abort condition.
    """
    missing = REQUIRED_FIELDS - set(record.keys())
    if missing:
        return False, f"missing fields: {missing}"

    if not isinstance(record["all_chunk_ids"], list) or not record["all_chunk_ids"]:
        return False, "all_chunk_ids must be a non-empty list"

    classification = record.get("classification", {})
    if not isinstance(classification, dict):
        return False, "classification must be a dict"

    if classification.get("routing_done") != "true":
        return False, f"classification.routing_done is '{classification.get('routing_done')}', expected 'true'"

    t1 = classification.get("primary_tier1", "")
    if t1 not in VALID_TIER1:
        return False, f"classification.primary_tier1 '{t1}' not in TAXONOMY"

    return True, "ok"


def write_record(
    record: dict,
    col_knowledge,
    col_facts,
    col_style,
    dry_run: bool,
) -> dict:
    """
    Write one validated record to ChromaDB. Returns status dict.
    ChromaDB update() merges into existing metadata — does not overwrite
    unrelated fields to null.
    """
    conv_id       = record["conv_id"]
    pair_idx      = record["pair_idx"]
    all_chunk_ids = record["all_chunk_ids"]
    user_text_raw = record["user_text_raw"]
    classification = dict(record["classification"])
    route_facts   = bool(record["route_facts"])
    route_style   = bool(record["route_style"])

    # Validate and coerce tier values — operator may have edited the JSONL
    t1 = classification.get("primary_tier1", "")
    t2 = classification.get("primary_tier2", "")
    t3 = classification.get("primary_tier3", "")
    t1, t2, t3 = validate_tier(t1, t2, t3, context=f"{conv_id}/{pair_idx}")
    classification["primary_tier1"] = t1
    classification["primary_tier2"] = t2
    classification["primary_tier3"] = t3
    classification["category"] = t1

    st1 = classification.get("secondary_tier1", "")
    st2 = classification.get("secondary_tier2", "")
    st3 = classification.get("secondary_tier3", "")
    if st1 and st1 in VALID_TIER1:
        st1, st2, st3 = validate_tier(st1, st2, st3, context=f"{conv_id}/{pair_idx} secondary")
        classification["secondary_tier1"] = st1
        classification["secondary_tier2"] = st2
        classification["secondary_tier3"] = st3

    wrote_fact = wrote_style = False

    if not dry_run:
        # Update all chunks in col_knowledge with classification metadata
        with _chroma_lock:
            for chunk_id in all_chunk_ids:
                try:
                    col_knowledge.update(ids=[chunk_id], metadatas=[classification])
                except Exception as e:
                    log.error(f"WRITE_KNOWLEDGE [{conv_id}/{pair_idx}] chunk {chunk_id}: {e}")
                    raise

        log.info(f"WRITE_KNOWLEDGE [{conv_id}/{pair_idx}]: {len(all_chunk_ids)} chunks updated")

        # Write to col_facts if routed and text is long enough
        if route_facts and len(user_text_raw) >= MIN_FACT_LEN:
            source = record.get("source", "")
            era    = record.get("era", "")
            title  = record.get("title", "")
            fact_meta = {
                **classification,
                "type":               "fact",
                "conv_id":            conv_id,
                "pair_idx":           str(pair_idx),
                "source":             source,
                "era":                era,
                "title":              title,
                "source_knowledge_id": all_chunk_ids[0],
            }
            with _chroma_lock:
                col_facts.upsert(
                    ids       = [f"fact_{conv_id}_{pair_idx}"],
                    documents = [user_text_raw],
                    metadatas = [fact_meta],
                )
            log.info(f"WRITE_FACT [{conv_id}/{pair_idx}]")
            wrote_fact = True

        # Write to col_style if routed and text is long enough
        if route_style and len(user_text_raw) >= MIN_STYLE_LEN:
            source = record.get("source", "")
            era    = record.get("era", "")
            title  = record.get("title", "")
            style_meta = {
                **classification,
                "type":               "style",
                "conv_id":            conv_id,
                "pair_idx":           str(pair_idx),
                "source":             source,
                "era":                era,
                "title":              title,
                "source_knowledge_id": all_chunk_ids[0],
            }
            with _chroma_lock:
                col_style.upsert(
                    ids       = [f"style_{conv_id}_{pair_idx}"],
                    documents = [user_text_raw],
                    metadatas = [style_meta],
                )
            log.info(f"WRITE_STYLE [{conv_id}/{pair_idx}]")
            wrote_style = True

    else:
        # Dry run: report what would happen
        fact_note  = f"fact=YES (len={len(user_text_raw)})" if (route_facts and len(user_text_raw) >= MIN_FACT_LEN) else "fact=NO"
        style_note = f"style=YES (len={len(user_text_raw)})" if (route_style and len(user_text_raw) >= MIN_STYLE_LEN) else "style=NO"
        print(f"  [DRY-RUN] {conv_id}/{pair_idx}: {len(all_chunk_ids)} chunks | {fact_note} | {style_note} | tier={t1}/{t2}/{t3}")

    return {"wrote_fact": wrote_fact, "wrote_style": wrote_style, "chunks": len(all_chunk_ids)}


def main():
    parser = argparse.ArgumentParser(description="Lucchese write_classifications")
    parser.add_argument("--input",   required=True, help="Path to classifications JSONL file")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print without writing")
    parser.add_argument("--source",  type=str, default=None, help="Filter to a specific source (chatgpt/grok)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: file not found: {input_path}")
        return

    print(f"\n{'─'*60}")
    print(f"Lucchese write_classifications")
    print(f"Input   : {input_path}")
    print(f"Dry run : {args.dry_run}")
    if args.source:
        print(f"Source  : {args.source} only")
    print(f"Log     : {_log_path}")
    print(f"{'─'*60}\n")

    log.info(f"=== WRITE START === input={input_path} dry_run={args.dry_run} source={args.source}")

    if not args.dry_run:
        _, col_knowledge, col_facts, col_style = get_collections()
    else:
        col_knowledge = col_facts = col_style = None

    stats = {"total": 0, "written": 0, "skipped": 0, "errors": 0}

    with open(input_path, "r", encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, start=1):
            raw_line = raw_line.strip()
            if not raw_line:
                continue

            stats["total"] += 1

            # Parse the line
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as e:
                log.warning(f"SKIP_INVALID [line {line_number}]: JSON parse error — {e} — raw: {raw_line[:80]}")
                stats["skipped"] += 1
                continue

            # Source filter
            if args.source and record.get("source") != args.source:
                stats["skipped"] += 1
                continue

            # Validate
            valid, reason = validate_record(record, line_number)
            if not valid:
                log.warning(f"SKIP_INVALID [line {line_number}]: {reason} — conv_id={record.get('conv_id', '?')} pair_idx={record.get('pair_idx', '?')}")
                stats["skipped"] += 1
                continue

            # Write
            try:
                result = write_record(record, col_knowledge, col_facts, col_style, dry_run=args.dry_run)
                stats["written"] += 1
            except Exception as e:
                log.error(f"WRITE_ERROR [line {line_number}] {record.get('conv_id', '?')}/{record.get('pair_idx', '?')}: {e}")
                stats["errors"] += 1

    summary = (
        f"WRITE COMPLETE: total={stats['total']} written={stats['written']} "
        f"skipped={stats['skipped']} errors={stats['errors']}"
    )
    print(f"\n{'─'*60}")
    if args.dry_run:
        print(f"[DRY-RUN] {summary}")
    else:
        print(f"✓ {summary}")
    print(f"  Log: {_log_path}")
    print(f"{'─'*60}\n")
    log.info(f"=== {summary} ===")


if __name__ == "__main__":
    main()

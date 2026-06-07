"""
reclassify.py  v2
─────────────────
Fixes applied from technical review of v1:

  FIX 1 (CRITICAL): Chunk-level classification duplicated facts/style entries
    v1 processed each ChromaDB chunk entry independently. An exchange producing
    3 chunks would create 3 fact entries and 3 style entries, all with identical
    user_text_raw — polluting both collections with duplicate embeddings.

    v2 groups entries by (conv_id, pair_idx) before classification:
      - Classifies ONCE per exchange (all chunks share the same user_text_raw)
      - Writes the classification back to ALL chunks in the group
      - Creates ONE fact entry:  fact_{conv_id}_{pair_idx}
      - Creates ONE style entry: style_{conv_id}_{pair_idx}
    Also saves LLM calls: 4 calls per exchange regardless of chunk count.

  FIX 2: Tier1 punctuation stripping
    v1 .split()[0] left punctuation attached ("technology." etc), causing silent
    fallback to "personal" on every punctuated model response.
    v2 strips non-alpha characters: re.sub(r"[^a-z_]", "", raw_word)

  FIX 3: Routing criteria tightened
    v1 prompt was too broad — covered almost everything Alex wrote.
    v2 requires first-person personal content for facts; argumentative voice
    for style. Task instructions excluded explicitly.

  FIX 4: excerpt_note dead code removed
    v1 appended a truncation note to assistant_ctx but all prompts then sliced
    it at [:250]/[:300], making the note invisible in every case.

  FIX 5: --wipe flag added
    v1 had no way to restart classification cleanly. v2 --wipe deletes all
    facts/style entries and resets routing_done='false' in knowledge.

DEDUP TODO (v3):
    Within-domain dedup after classification is not yet implemented.
    See ingest docstrings for design notes.

CONTRACT WITH INGEST:
    Documents in col_knowledge may contain [prior: ...] prefixes.
    Always read user_text_raw from metadata. Never use the document field.
    pair_idx is stored as a string — cast to int when sorting.

USAGE:
    python reclassify.py
    python reclassify.py --limit 20           # test on first 20 exchange groups
    python reclassify.py --source chatgpt     # chatgpt entries only
    python reclassify.py --source grok        # grok entries only
    python reclassify.py --wipe               # reset all classification
"""

import json
import argparse
import logging
import re
import threading
import asyncio
import httpx
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
load_dotenv()

from pipeline.shared import (
    safe_json as _shared_safe_json,
    llm_call as _shared_llm_call,
    validate_tier as _shared_validate_tier,
    TAXONOMY,
    VALID_TIER1,
    TIER_SAFE_DEFAULTS,
    make_logger,
)


CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
EMBED_MODEL  = "nomic-ai/nomic-embed-text-v1"
BATCH_SIZE   = 20
CONCURRENCY  = 4

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/api/chat"
MODEL      = os.getenv("MODEL_FAST", "gemma2:27b")

MIN_FACT_LEN  = 50
MIN_STYLE_LEN = 100

_chroma_lock = threading.Lock()
_semaphore: asyncio.Semaphore | None = None

_jsonl_lock: threading.Lock = threading.Lock()
_jsonl_path: Path | None    = None


_log_path = Path(f"reclassify_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
log = make_logger("lucchese_reclassify", _log_path)

ONTOLOGY_CLASSES   = ["gnosis", "episteme", "pistis", "doxa", "logos", "techne"]
VALID_SOURCE_TYPES = ["self", "dialogue", "received", "generated"]

def valid_tier2(t1):  return list(TAXONOMY.get(t1, {}).keys())
def valid_tier3(t1, t2): return TAXONOMY.get(t1, {}).get(t2, [])
def taxonomy_tier1_options(): return ", ".join(VALID_TIER1)

def taxonomy_tier2_reference(t1):
    return "\n".join(f"  {t2} -> [{', '.join(t3s)}]"
                     for t2, t3s in TAXONOMY.get(t1, {}).items())

def taxonomy_secondary_reference(exclude_t1=""):
    return "\n".join(f"  {t1} -> [{', '.join(t2s.keys())}]"
                     for t1, t2s in TAXONOMY.items() if t1 != exclude_t1)

def get_collections():
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL, trust_remote_code=True)
    client        = chromadb.PersistentClient(path=CHROMA_PATH)
    col_knowledge = client.get_or_create_collection("knowledge", embedding_function=ef)
    col_facts     = client.get_or_create_collection("facts",     embedding_function=ef)
    col_style     = client.get_or_create_collection("style",     embedding_function=ef)
    return client, ef, col_knowledge, col_facts, col_style


async def llm_call(client, prompt, max_tokens=80):
    """Wrapper: passes module semaphore/url/model to shared llm_call."""
    assert _semaphore is not None
    result = await _shared_llm_call(client, prompt, max_tokens, _semaphore, OLLAMA_URL, MODEL)
    if not result:
        log.error("LLM call failed after 3 attempts")
    return result


_TIER1_PROMPT = """Classify this conversation into exactly one subject area.

Valid categories: {tier1_options}

[Alex]: {user_text}
[Assistant]: {assistant_excerpt}

Reply with one word only - the category name. No punctuation. No explanation."""

_TIER23_PROMPT = """This conversation falls under "{tier1}". Classify it further.

Available paths for {tier1}:
{tier2_ref}

[Alex]: {user_text}
[Assistant]: {assistant_excerpt}

If this genuinely spans a second subject domain, choose SECONDARY tier1+tier2 from:
{secondary_ref}

Reply with JSON only:
{{
  "primary_tier2": "...",
  "primary_tier3": "...",
  "secondary_tier1": "",
  "secondary_tier2": "",
  "secondary_tier3": "",
  "is_personal": true
}}

is_personal = true only if this is specifically about Alex's own life, opinions, or situation.
Leave secondary fields as empty strings if no second domain applies."""

_ONTOLOGY_PROMPT = """Classify the primary nature of this knowledge and its epistemological source.

Ontology classes:
  gnosis   - Alex's direct personal experience or lived knowledge.
  episteme - Intellectual understanding through reasoning or study.
  pistis   - Belief or conviction held without direct proof.
  doxa     - Received wisdom, cultural assumption, or general opinion.
  logos    - Systematic understanding of how something works mechanically.
  techne   - Practical skill or procedural knowledge.

source_type:
  self      - Alex expressing his own lived experience, opinion, or belief
  dialogue  - Knowledge that emerged through the back-and-forth exchange
  received  - Alex receiving information or explanation from the AI
  generated - Purely AI output, no personal content from Alex

[Alex]: {user_text}
[Assistant]: {assistant_excerpt}

Reply with JSON only:
{{"ontology": "episteme", "source_type": "received"}}"""

_ROUTING_PROMPT = """Decide storage routing for this message from Alex's conversation history.

facts = true ONLY if Alex's message contains something specifically personal:
        his own stated opinion, a first-person belief, or a fact about his own life.
        false for: task instructions, code requests, information-seeking questions.
        Example TRUE:  "I genuinely think the NHS is broken from the inside out"
        Example TRUE:  "I've run 5/3/1 for two years and my squat has completely stalled"
        Example FALSE: "Write me a Python function to parse this JSON"
        Example FALSE: "What's the best way to reheat meal prep rice?"

style = true ONLY if the message shows Alex's argumentative or analytical voice -
        he is making a case, pushing back, speculating, or reasoning at length.
        Must be 40+ words. false for questions, one-liners, task instructions.
        Example TRUE:  [long opinionated message challenging mainstream advice]
        Example FALSE: "thanks" / "ok do that" / "what about X?"

engagement = "active" if Alex pushed back or drove the direction with his own opinions.
           = "passive" if Alex asked once and accepted the reply.

[Alex]: {user_text}
[Assistant]: {assistant_excerpt}

Reply with JSON only:
{{"facts": false, "style": false, "engagement": "passive"}}"""


async def _classify_tier1(client, user_text, assistant_excerpt, entry_id):
    prompt   = _TIER1_PROMPT.format(
        tier1_options=taxonomy_tier1_options(),
        user_text=user_text[:400],
        assistant_excerpt=assistant_excerpt[:250],
    )
    response = await llm_call(client, prompt, max_tokens=10)
    # FIX 2: strip non-alpha chars before validation
    raw_word = response.lower().strip().split()[0] if response.strip() else ""
    t1       = re.sub(r"[^a-z_]", "", raw_word)
    if t1 not in VALID_TIER1:
        log.warning(f"TIER1 [{entry_id}]: '{t1}' (raw: '{raw_word}') -> 'personal'")
        return TIER_SAFE_DEFAULTS["personal"][0]
    log.debug(f"TIER1 [{entry_id}]: '{t1}'")
    return t1


async def _classify_tier23(client, t1, user_text, assistant_excerpt, entry_id):
    prompt = _TIER23_PROMPT.format(
        tier1=t1, tier2_ref=taxonomy_tier2_reference(t1),
        secondary_ref=taxonomy_secondary_reference(exclude_t1=t1),
        user_text=user_text[:400], assistant_excerpt=assistant_excerpt[:250],
    )
    result  = safe_json(await llm_call(client, prompt, max_tokens=120))
    pt1, pt2, pt3 = validate_tier(
        t1,
        result.get("primary_tier2",  TIER_SAFE_DEFAULTS[t1][1]),
        result.get("primary_tier3",  TIER_SAFE_DEFAULTS[t1][2]),
        context=f"{entry_id} primary",
    )
    st1 = result.get("secondary_tier1", "")
    st2 = result.get("secondary_tier2", "")
    st3 = result.get("secondary_tier3", "")
    if st1:
        st1, st2, st3 = validate_tier(st1, st2, st3, context=f"{entry_id} secondary")
    log.debug(f"TIER23 [{entry_id}]: {pt1}/{pt2}/{pt3} secondary={st1 or 'none'}")
    return {
        "primary_tier1": pt1, "primary_tier2": pt2, "primary_tier3": pt3,
        "secondary_tier1": st1, "secondary_tier2": st2, "secondary_tier3": st3,
        "is_personal": str(result.get("is_personal", False)).lower(),
    }


async def _classify_ontology(client, user_text, assistant_excerpt, entry_id):
    prompt   = _ONTOLOGY_PROMPT.format(user_text=user_text[:400], assistant_excerpt=assistant_excerpt[:300])
    result   = safe_json(await llm_call(client, prompt, max_tokens=30))
    ontology = result.get("ontology", "").lower().strip()
    source   = result.get("source_type", "").lower().strip()
    if ontology not in ONTOLOGY_CLASSES:
        log.warning(f"ONTOLOGY [{entry_id}]: '{ontology}' -> 'unknown'")
        ontology = "unknown"
    if source not in VALID_SOURCE_TYPES:
        log.warning(f"SOURCE_TYPE [{entry_id}]: '{source}' -> 'received'")
        source = "received"
    log.debug(f"ONTOLOGY [{entry_id}]: '{ontology}' source='{source}'")
    return ontology, source


async def _classify_routing(client, user_text, assistant_excerpt, entry_id):
    prompt     = _ROUTING_PROMPT.format(user_text=user_text[:400], assistant_excerpt=assistant_excerpt[:250])
    result     = safe_json(await llm_call(client, prompt, max_tokens=40))
    engagement = result.get("engagement", "passive")
    if engagement not in ("active", "passive"):
        log.warning(f"ROUTING [{entry_id}]: '{engagement}' -> 'passive'")
        engagement = "passive"
    routing = {"facts": bool(result.get("facts", False)),
               "style": bool(result.get("style", False)),
               "engagement": engagement}
    log.debug(f"ROUTING [{entry_id}]: {routing}")
    return routing


async def classify_exchange(representative_id, meta, client):
    """
    Classify one exchange (4 LLM calls in 2 concurrent waves).
    FIX 4: removed excerpt_note dead code from v1.
    """
    user_text         = meta.get("user_text_raw", "").strip()
    assistant_excerpt = meta.get("assistant_excerpt", "").strip()

    if not user_text:
        log.warning(f"CLASSIFY [{representative_id}]: no user_text_raw -> defaults")
        safe = TIER_SAFE_DEFAULTS["personal"]
        return {"ontology": "unknown", "source_type": "received", "engagement": "passive",
                "is_personal": "false", "primary_tier1": safe[0], "primary_tier2": safe[1],
                "primary_tier3": safe[2], "secondary_tier1": "", "secondary_tier2": "",
                "secondary_tier3": "", "category": safe[0], "routing_done": "true",
                "_facts": False, "_style": False}

    # Wave 1: tier1 + ontology concurrently
    t1, (ontology, source_type) = await asyncio.gather(
        _classify_tier1(client, user_text, assistant_excerpt, representative_id),
        _classify_ontology(client, user_text, assistant_excerpt, representative_id),
    )

    # Wave 2: tier23 + routing concurrently
    taxonomy, routing = await asyncio.gather(
        _classify_tier23(client, t1, user_text, assistant_excerpt, representative_id),
        _classify_routing(client, user_text, assistant_excerpt, representative_id),
    )

    return {
        "ontology":        ontology,        "source_type":     source_type,
        "engagement":      routing["engagement"], "is_personal": taxonomy["is_personal"],
        "primary_tier1":   taxonomy["primary_tier1"], "primary_tier2": taxonomy["primary_tier2"],
        "primary_tier3":   taxonomy["primary_tier3"], "secondary_tier1": taxonomy["secondary_tier1"],
        "secondary_tier2": taxonomy["secondary_tier2"], "secondary_tier3": taxonomy["secondary_tier3"],
        "category":        taxonomy["primary_tier1"],
        "routing_done":    "true",
        "_facts":          routing["facts"],
        "_style":          routing["style"],
    }


def group_entries_by_exchange(all_ids, all_metas):
    """FIX 1: Group chunk entries by (conv_id, pair_idx) exchange key."""
    groups      = defaultdict(list)
    ungroupable = []
    for entry_id, meta in zip(all_ids, all_metas):
        conv_id  = meta.get("conv_id", "")
        pair_idx = meta.get("pair_idx", "")
        if conv_id and pair_idx != "":
            groups[(conv_id, str(pair_idx))].append((entry_id, meta))
        else:
            ungroupable.append((entry_id, meta))
    if ungroupable:
        log.warning(f"GROUP: {len(ungroupable)} entries ungroupable -> classifying independently")
    return dict(groups), ungroupable


def _write_group_sync(conv_id, pair_idx, entries, classification, route_facts, route_style,
                      col_knowledge, col_facts, col_style):
    """
    FIX 1: Write classification to ALL chunks, create ONE fact/style entry per exchange.
    Fact ID:  fact_{conv_id}_{pair_idx}
    Style ID: style_{conv_id}_{pair_idx}
    """
    user_text_raw = entries[0][1].get("user_text_raw", "")

    with _chroma_lock:
        for entry_id, meta in entries:
            col_knowledge.update(ids=[entry_id], metadatas=[{**meta, **classification}])

    wrote_fact = wrote_style = False

    if route_facts and len(user_text_raw) >= MIN_FACT_LEN:
        fact_meta = {**entries[0][1], **classification, "type": "fact",
                     "source_knowledge_id": entries[0][0]}
        with _chroma_lock:
            col_facts.upsert(ids=[f"fact_{conv_id}_{pair_idx}"],
                             documents=[user_text_raw], metadatas=[fact_meta])
        wrote_fact = True

    if route_style and len(user_text_raw) >= MIN_STYLE_LEN:
        style_meta = {**entries[0][1], **classification, "type": "style",
                      "source_knowledge_id": entries[0][0]}
        with _chroma_lock:
            col_style.upsert(ids=[f"style_{conv_id}_{pair_idx}"],
                             documents=[user_text_raw], metadatas=[style_meta])
        wrote_style = True

    return {"facts": wrote_fact, "style": wrote_style, "chunks": len(entries)}


async def process_group(group_key, entries, client, col_knowledge):
    """Classify all chunks of one exchange as a single unit."""
    conv_id, pair_idx      = group_key
    representative_id, rep_meta = entries[0]
    try:
        classification = await classify_exchange(representative_id, rep_meta, client)
        route_facts    = classification.pop("_facts", False)
        route_style    = classification.pop("_style", False)
        record = {
            "conv_id":              conv_id,
            "pair_idx":             pair_idx,
            "representative_chunk_id": representative_id,
            "all_chunk_ids":        [eid for eid, _ in entries],
            "user_text_raw":        rep_meta.get("user_text_raw", ""),
            "classification":       classification,
            "route_facts":          route_facts,
            "route_style":          route_style,
            "source":               rep_meta.get("source", ""),
            "created_at":           rep_meta.get("created_at", ""),
            "era":                  rep_meta.get("era", ""),
            "title":                rep_meta.get("title", ""),
        }
        def _append_jsonl():
            with _jsonl_lock:
                with open(_jsonl_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record) + "\n")
        await asyncio.to_thread(_append_jsonl)
        return {"error": False, "chunks": len(entries)}

    except Exception as e:
        import traceback
        log.error(f"GROUP CRASH [{conv_id}/{pair_idx}]: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        return {"error": True, "chunks": len(entries)}



def wipe_classification(col_knowledge, col_facts, col_style, source=None):
    """FIX 5: Delete facts/style and reset routing_done in knowledge."""
    print(f"Wiping classification{'  (source: '+source+')' if source else ''}...")
    FETCH_SIZE = 500
    where_src  = {"source": source} if source else None

    for col, name in [(col_facts, "facts"), (col_style, "style")]:
        try:
            all_ids, offset = [], 0
            while True:
                kw = {"limit": FETCH_SIZE, "offset": offset}
                if where_src:
                    kw["where"] = where_src
                r = col.get(**kw)
                if not r["ids"]:
                    break
                all_ids.extend(r["ids"])
                offset += FETCH_SIZE
            if all_ids:
                with _chroma_lock:
                    col.delete(ids=all_ids)
                print(f"  Deleted {len(all_ids)} from col_{name}")
            else:
                print(f"  col_{name} already empty")
        except Exception as e:
            print(f"  Error clearing col_{name}: {e}")

    try:
        all_ids, all_metas, offset = [], [], 0
        while True:
            where = {"routing_done": {"$eq": "true"}}
            if source:
                where = {"$and": [{"routing_done": {"$eq": "true"}}, {"source": {"$eq": source}}]}
            b = col_knowledge.get(where=where, limit=FETCH_SIZE, offset=offset, include=["metadatas"])
            if not b["ids"]:
                break
            all_ids.extend(b["ids"])
            all_metas.extend(b["metadatas"])
            offset += FETCH_SIZE
        if all_ids:
            for i in range(0, len(all_ids), 200):
                bids = all_ids[i:i+200]
                bmetas = [{**m, "routing_done": "false", "category": "unclassified",
                           "ontology": "unclassified", "source_type": "unclassified",
                           "primary_tier1": "unclassified", "primary_tier2": "unclassified",
                           "primary_tier3": "unclassified", "engagement": "unclassified",
                           "is_personal": "unclassified"} for m in all_metas[i:i+200]]
                with _chroma_lock:
                    col_knowledge.update(ids=bids, metadatas=bmetas)
            print(f"  Reset routing_done for {len(all_ids)} knowledge entries")
        else:
            print("  No classified entries to reset")
    except Exception as e:
        print(f"  Error resetting knowledge: {e}")
    print("  Wipe complete\n")


async def main():
    global _semaphore

    parser = argparse.ArgumentParser(description="Lucchese Reclassify v2")
    parser.add_argument("--limit",  type=int, default=None)
    parser.add_argument("--source", type=str, default=None)
    parser.add_argument("--wipe",   action="store_true")
    args = parser.parse_args()

    _semaphore = asyncio.Semaphore(CONCURRENCY)

    print(f"\n{'─'*60}")
    print(f"Lucchese Reclassify v2")
    print(f"Model       : {MODEL}")
    print(f"Concurrency : {CONCURRENCY}")
    print(f"Batch size  : {BATCH_SIZE} exchange groups")
    print(f"Log         : {_log_path}")
    if args.source: print(f"Source      : {args.source} only")
    if args.limit:  print(f"Limit       : {args.limit} groups [TEST MODE]")
    if args.wipe:   print(f"Mode        : WIPE")
    print(f"{'─'*60}\n")

    log.info(f"=== RECLASSIFY START === model={MODEL} source={args.source} limit={args.limit} wipe={args.wipe}")

    _, _, col_knowledge, col_facts, col_style = get_collections()

    if args.wipe:
        wipe_classification(col_knowledge, col_facts, col_style, source=args.source)
        if not args.limit:
            print("Wipe complete. Re-run without --wipe to classify.")
            return

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    async with httpx.AsyncClient() as client:
        try:
            await client.get(base_url, timeout=5)
            print("✓ Ollama reachable\n")
        except Exception:
            print("✗ Ollama unreachable")
            return

                 # Set JSONL output path before any processing begins.
        # If the file cannot be created, abort before classifying anything.
        global _jsonl_path
        _jsonl_path = Path(f"classifications_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl")
        try:
            _jsonl_path.touch()
        except Exception as e:
            print(f"✗ Cannot create JSONL output file {_jsonl_path}: {e}")
            log.error(f"JSONL file creation failed: {e}")
            return



        print("Fetching unclassified entries...")
        where_clause = ({"$and": [{"routing_done": {"$eq": "false"}}, {"source": {"$eq": args.source}}]}
                        if args.source else {"routing_done": {"$eq": "false"}})

        all_ids, all_metas, offset = [], [], 0
        while True:
            try:
                b = col_knowledge.get(where=where_clause, limit=500, offset=offset, include=["metadatas"])
            except Exception as e:
                log.error(f"Fetch error at offset {offset}: {e}")
                print(f"  Fetch error: {e}")
                break
            if not b["ids"]:
                break
            all_ids.extend(b["ids"])
            all_metas.extend(b["metadatas"])
            offset += 500
            print(f"  Fetched {len(all_ids)} chunks...", end="\r")

        print(f"\nChunks fetched: {len(all_ids)}")

        if not all_ids:
            print("\nNothing to classify.")
            total = col_knowledge.count()
            print(f"Total entries in col_knowledge: {total}")
            if total > 0:
                s = col_knowledge.get(limit=1, include=["metadatas"])
                if s["metadatas"]:
                    rd = s["metadatas"][0].get("routing_done", "FIELD MISSING")
                    print(f"Sample routing_done: '{rd}'")
                    if rd == "FIELD MISSING":
                        print("routing_done missing — entries from old ingest format. Re-ingest with v9/v2.")
            return

        groups, ungroupable = group_entries_by_exchange(all_ids, all_metas)
        sorted_groups = sorted(groups.items(),
                               key=lambda x: (x[0][0], int(x[0][1]) if x[0][1].isdigit() else 0))

        print(f"Exchange groups: {len(sorted_groups)}")
        if ungroupable:
            print(f"Ungroupable: {len(ungroupable)}")
            for idx, (eid, meta) in enumerate(ungroupable):
                sorted_groups.append((( f"_ug_{idx}", "0"), [(eid, meta)]))

        if args.limit:
            sorted_groups = sorted_groups[:args.limit]
            print(f"[TEST MODE] Limited to {args.limit} groups\n")

        total = len(sorted_groups)
        print(f"\nProcessing {total} exchange groups...\n")
        log.info(f"Processing {total} groups ({len(all_ids)} chunks)")

        stats = {"exchanges": 0, "chunks": 0, "errors": 0}

        for batch_start in range(0, total, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, total)
            batch     = sorted_groups[batch_start:batch_end]
            tasks     = [process_group(k, e, client, col_knowledge)
                         for k, e in batch]
            results   = await asyncio.gather(*tasks)

            for r in results:
                stats["exchanges"] += 1
                stats["chunks"]    += r.get("chunks", 1)
                if r["error"]:  stats["errors"] += 1

            pct = batch_end / total * 100
            print(f"  {batch_end}/{total} ({pct:.0f}%) | "
                  f"exchanges={stats['exchanges']} errors={stats['errors']} "
            log.info(f"BATCH {batch_start+1}-{batch_end} | stats={stats}")

    print(f"\n{'─'*60}")
    print(f"✓ Complete")
    print(f"  Exchanges classified : {stats['exchanges']}")
    print(f"  Chunks updated       : {stats['chunks']}")
    print(f"  Errors               : {stats['errors']}")
    print(f"\n  Log: {_log_path}")
    print(f"\nOutput : {_jsonl_path}")
    print(f"Review {_jsonl_path} before running write_classifications.py")
    print(f"Next   : python pipeline/write_classifications.py --input {_jsonl_path}")

    print(f"{'─'*60}\n")
    log.info(f"=== RECLASSIFY COMPLETE === jsonl={_jsonl_path} stats={stats}")



if __name__ == "__main__":
    asyncio.run(main())

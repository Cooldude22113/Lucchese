"""
inspect_memory.py
Standalone ChromaDB inspection tool for Lucchese.

Run from backend/ with venv active. No server required.

Commands:
    python inspect_memory.py stats
    python inspect_memory.py sample [--col knowledge|facts|style|documents|summaries]
                                    [--tier TIER] [--source SOURCE]
                                    [--routing done|pending|all]
                                    [--limit N] [--offset N]
    python inspect_memory.py search QUERY [--col COLLECTION|all] [--limit N]
    python inspect_memory.py live [--routing done|pending|all] [--limit N] [--conv CONV_ID]

Global flags:
    --log PATH   Write output to a UTF-8 file as well as the terminal.
                 Example: python inspect_memory.py stats --log stats.txt
"""

import argparse
import sys
import io
import chromadb

CHROMA_PATH = "./chroma_db"
COLLECTIONS = ["knowledge", "facts", "style", "documents", "summaries"]
SEP = "-" * 70


# ── Logging / Tee ─────────────────────────────────────────────────────────────

class _Tee:
    """Write to multiple streams simultaneously."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            try:
                s.write(data)
            except Exception:
                pass

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass

    def fileno(self):
        # Return the fileno of the first real stream so things like
        # isatty() checks don't break.
        return self.streams[0].fileno()


def enable_log(path: str) -> None:
    """
    Redirect stdout so output goes to both the terminal and a UTF-8 log file.
    Must be called before any print() statements.
    """
    log_file = open(path, "w", encoding="utf-8", errors="replace")

    # Wrap the underlying binary buffer in a UTF-8 TextIOWrapper so the
    # terminal side is also safe on Windows cp1252 environments.
    try:
        utf8_stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )
    except AttributeError:
        # sys.stdout.buffer not available in some environments — fall back.
        utf8_stdout = sys.stdout

    sys.stdout = _Tee(utf8_stdout, log_file)
    print(f"[inspect_memory] Logging to: {path}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_col(client, name):
    try:
        return client.get_collection(name)
    except Exception:
        return None


def print_entry(meta, doc, idx=None, dist=None):
    print(SEP)
    header = f"Entry #{idx}" if idx is not None else ""
    if dist is not None:
        header += f"  [relevance: {1/(1+dist):.2f}]"
    if header:
        print(header)

    print(f"Source   : {meta.get('source', '')}  |  Conv: {meta.get('conv_id', '')[:20]}")
    print(f"Tier     : {meta.get('primary_tier1', '')} / {meta.get('primary_tier2', '')} / {meta.get('primary_tier3', '')}")
    print(f"Category : {meta.get('category', '')}  |  Ontology: {meta.get('ontology', '')}  |  source_type: {meta.get('source_type', '')}")
    print(f"Type     : {meta.get('type', '')}  |  Personal: {meta.get('is_personal', '')}  |  Engagement: {meta.get('engagement', '')}")
    print(f"Routing  : {meta.get('routing_done', '')}  |  Era: {meta.get('era', '')}")
    print(f"Created  : {meta.get('created_at', '')}  |  Ingested: {meta.get('ingested_at', '')}")

    filename = meta.get("filename", "")
    if filename:
        print(f"File     : {filename}  |  chunk: {meta.get('chunk_idx', '')}")

    user_text = meta.get("user_text_raw", "") or doc or ""
    assistant = meta.get("assistant_excerpt", "")

    print(f"\nText     :\n{user_text[:1500]}")
    if assistant:
        print(f"\nAssistant:\n{assistant[:1000]}")


# ── stats ──────────────────────────────────────────────────────────────────────

def cmd_stats(client):
    print(f"\n{'='*70}")
    print("  COLLECTION COUNTS")
    print(f"{'='*70}")
    for name in COLLECTIONS:
        col = get_col(client, name)
        count = col.count() if col else 0
        label = "(not found)" if not col else f"{count:,}"
        print(f"  {name:<14}: {label}")

    col_k = get_col(client, "knowledge")
    if not col_k or col_k.count() == 0:
        return

    print(f"\n{'='*70}")
    print("  KNOWLEDGE BREAKDOWN  (scanning full collection - may take a moment)")
    print(f"{'='*70}")

    try:
        all_entries = col_k.get(limit=100_000, include=["metadatas"])
        metas = all_entries["metadatas"]

        routing_counts = {"done": 0, "pending": 0, "other": 0}
        tier_counts    = {}
        source_counts  = {}
        ontology_counts = {}

        for m in metas:
            rd = m.get("routing_done", "")
            if rd == "true":
                routing_counts["done"] += 1
            elif rd == "false":
                routing_counts["pending"] += 1
            else:
                routing_counts["other"] += 1

            t = m.get("primary_tier1", "unknown")
            tier_counts[t] = tier_counts.get(t, 0) + 1

            s = m.get("source", "unknown")
            source_counts[s] = source_counts.get(s, 0) + 1

            o = m.get("ontology", "")
            if o:
                ontology_counts[o] = ontology_counts.get(o, 0) + 1

        print(f"\nRouting done   : {routing_counts['done']:,}")
        print(f"Routing pending: {routing_counts['pending']:,}")

        print(f"\n-- Tier1 distribution --")
        for tier, count in sorted(tier_counts.items(), key=lambda x: -x[1]):
            print(f"  {tier:<25}: {count:,}")

        print(f"\n-- Source distribution --")
        for src, count in sorted(source_counts.items(), key=lambda x: -x[1]):
            print(f"  {src:<20}: {count:,}")

        if ontology_counts:
            print(f"\n-- Ontology distribution (knowledge) --")
            for ont, count in sorted(ontology_counts.items(), key=lambda x: -x[1]):
                print(f"  {ont:<20}: {count:,}")

    except Exception as e:
        print(f"  Error scanning knowledge: {e}")

    # Also show ontology breakdown for facts collection
    col_f = get_col(client, "facts")
    if col_f and col_f.count() > 0:
        print(f"\n{'='*70}")
        print("  FACTS BREAKDOWN")
        print(f"{'='*70}")
        try:
            all_facts = col_f.get(limit=100_000, include=["metadatas"])
            fmetas = all_facts["metadatas"]

            f_ontology  = {}
            f_tier      = {}
            f_personal  = {"true": 0, "false": 0, "unknown": 0}
            f_source    = {}

            for m in fmetas:
                o = m.get("ontology", "")
                f_ontology[o or "none"] = f_ontology.get(o or "none", 0) + 1

                t = m.get("primary_tier1", "unknown")
                f_tier[t] = f_tier.get(t, 0) + 1

                p = str(m.get("is_personal", "")).lower()
                if p == "true":
                    f_personal["true"] += 1
                elif p == "false":
                    f_personal["false"] += 1
                else:
                    f_personal["unknown"] += 1

                s = m.get("source", "unknown")
                f_source[s] = f_source.get(s, 0) + 1

            print(f"\n-- Ontology distribution (facts) --")
            for ont, count in sorted(f_ontology.items(), key=lambda x: -x[1]):
                print(f"  {ont:<20}: {count:,}")

            print(f"\n-- Tier1 distribution (facts) --")
            for tier, count in sorted(f_tier.items(), key=lambda x: -x[1]):
                print(f"  {tier:<25}: {count:,}")

            print(f"\n-- is_personal (facts) --")
            print(f"  true   : {f_personal['true']:,}")
            print(f"  false  : {f_personal['false']:,}")
            print(f"  unknown: {f_personal['unknown']:,}")

            print(f"\n-- Source distribution (facts) --")
            for src, count in sorted(f_source.items(), key=lambda x: -x[1]):
                print(f"  {src:<20}: {count:,}")

        except Exception as e:
            print(f"  Error scanning facts: {e}")


# ── sample ─────────────────────────────────────────────────────────────────────

def build_where(tier, source, routing, ontology, col_name):
    filters = []
    if routing != "all" and col_name == "knowledge":
        filters.append({"routing_done": {"$eq": "true" if routing == "done" else "false"}})
    if tier:
        filters.append({"primary_tier1": {"$eq": tier}})
    if source:
        filters.append({"source": {"$eq": source}})
    if ontology:
        filters.append({"ontology": {"$eq": ontology}})

    if not filters:
        return None
    if len(filters) == 1:
        return filters[0]
    return {"$and": filters}


def cmd_sample(client, col_name, tier, source, routing, ontology, limit, offset):
    col = get_col(client, col_name)
    if not col:
        print(f"Collection '{col_name}' not found.")
        return

    where = build_where(tier, source, routing, ontology, col_name)
    kwargs = {"limit": limit, "offset": offset, "include": ["documents", "metadatas"]}
    if where:
        kwargs["where"] = where

    try:
        results = col.get(**kwargs)
    except Exception as e:
        print(f"Error: {e}")
        return

    ids   = results["ids"]
    docs  = results["documents"]
    metas = results["metadatas"]
    total = col.count()

    filters_desc = "  ".join(filter(None, [
        f"tier={tier}"         if tier     else "",
        f"source={source}"     if source   else "",
        f"ontology={ontology}" if ontology else "",
        f"routing={routing}"   if routing != "all" else "",
    ])) or "no filters"

    print(f"\n-- {col_name} | {filters_desc} | offset {offset} | showing {len(ids)} of ~{total} total --")

    if not ids:
        print("No entries match.")
        return

    for i, (doc, meta) in enumerate(zip(docs, metas)):
        print_entry(meta, doc, idx=offset + i + 1)

    print(SEP)
    next_offset = offset + limit
    print(f"Shown {offset+1}-{offset+len(ids)}. Next page: --offset {next_offset}")


# ── search ─────────────────────────────────────────────────────────────────────

def cmd_search(client, query, col_name, limit):
    cols_to_search = [c for c in COLLECTIONS if c != "summaries"] if col_name == "all" else [col_name]

    print(f"\nSearching: '{query}'  in: {', '.join(cols_to_search)}")

    for name in cols_to_search:
        col = get_col(client, name)
        if not col or col.count() == 0:
            continue

        try:
            n = min(limit, col.count())
            results = col.query(
                query_texts=[query],
                n_results=n,
                include=["documents", "distances", "metadatas"],
            )
            ids   = results["ids"][0]
            docs  = results["documents"][0]
            metas = results["metadatas"][0]
            dists = results["distances"][0]

            print(f"\n{'='*70}")
            print(f"  {name.upper()}  ({len(ids)} hits)")
            print(f"{'='*70}")

            for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists)):
                print_entry(meta, doc, idx=i + 1, dist=dist)

        except Exception as e:
            print(f"  {name}: error - {e}")

    print(SEP)


# ── live ───────────────────────────────────────────────────────────────────────

def cmd_live(client, routing, limit, conv_id):
    col = get_col(client, "knowledge")
    if not col or col.count() == 0:
        print("knowledge collection is empty.")
        return

    where_filters = [{"source": {"$eq": "lucchese"}}]
    if routing != "all":
        where_filters.append({"routing_done": {"$eq": "true" if routing == "done" else "false"}})
    if conv_id:
        where_filters.append({"conv_id": {"$eq": conv_id}})

    where = {"$and": where_filters} if len(where_filters) > 1 else where_filters[0]

    try:
        results = col.get(limit=100_000, where=where, include=["metadatas"])
    except Exception as e:
        print(f"Error: {e}")
        return

    seen = {}
    for meta in results["metadatas"]:
        key = (meta.get("conv_id", ""), meta.get("pair_idx", ""))
        if key not in seen:
            seen[key] = meta

    exchanges = sorted(seen.values(), key=lambda m: m.get("created_at", ""), reverse=True)
    exchanges = exchanges[:limit]

    total_chunks    = len(results["metadatas"])
    total_exchanges = len(seen)

    print(f"\n-- live lucchese ingestions | routing={routing} | {total_exchanges} exchanges / {total_chunks} chunks --")
    if conv_id:
        print(f"   filtered to conv_id: {conv_id}")

    for i, meta in enumerate(exchanges):
        print(SEP)
        print(f"Exchange #{i+1}  [{meta.get('created_at', '')}]")
        print(f"Conv     : {meta.get('conv_id', '')}  |  pair: {meta.get('pair_idx', '')}")
        print(f"Routing  : {meta.get('routing_done', '')}  |  Tier: {meta.get('primary_tier1', '')} / {meta.get('primary_tier2', '')}")
        user_text = meta.get("user_text_raw", "")
        assistant = meta.get("assistant_excerpt", "")
        print(f"\nYou      :\n{user_text[:1500]}")
        if assistant:
            print(f"\nLucchese :\n{assistant[:1000]}")

    print(SEP)
    print(f"Shown {len(exchanges)} of {total_exchanges} exchanges. Use --limit to see more.")


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Inspect Lucchese ChromaDB memory entries.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--log", type=str, default=None, metavar="PATH",
        help="Write output to a UTF-8 file as well as the terminal.",
    )

    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("stats", help="Counts, routing/ontology/tier/source breakdowns for all collections.")

    sp = sub.add_parser("sample", help="Browse actual entries with optional filters.")
    sp.add_argument("--col",      default="knowledge", choices=COLLECTIONS)
    sp.add_argument("--tier",     help="Filter by primary_tier1  e.g. personal, health, finance")
    sp.add_argument("--source",   help="Filter by source  e.g. chatgpt, grok, lucchese")
    sp.add_argument("--ontology", help="Filter by ontology class  e.g. gnosis, pistis, doxa, logos, techne, episteme")
    sp.add_argument("--routing",  choices=["done", "pending", "all"], default="all",
                    help="Routing status filter (knowledge only)")
    sp.add_argument("--limit",  type=int, default=10)
    sp.add_argument("--offset", type=int, default=0)

    ss = sub.add_parser("search", help="Semantic search and show matching entries.")
    ss.add_argument("query")
    ss.add_argument("--col",   default="all", choices=COLLECTIONS + ["all"])
    ss.add_argument("--limit", type=int, default=5, help="Results per collection")

    sl = sub.add_parser("live", help="Recent live Lucchese ingestions, one entry per exchange.")
    sl.add_argument("--routing", choices=["done", "pending", "all"], default="all")
    sl.add_argument("--limit",   type=int, default=20, help="Number of exchanges to show")
    sl.add_argument("--conv",    help="Filter to a specific conv_id")

    args = parser.parse_args()

    if args.log:
        enable_log(args.log)

    if not args.cmd:
        parser.print_help()
        return

    client = chromadb.PersistentClient(path=CHROMA_PATH)

    if args.cmd == "stats":
        cmd_stats(client)
    elif args.cmd == "sample":
        cmd_sample(
            client, args.col, args.tier, args.source,
            args.routing, args.ontology, args.limit, args.offset,
        )
    elif args.cmd == "search":
        cmd_search(client, args.query, args.col, args.limit)
    elif args.cmd == "live":
        cmd_live(client, args.routing, args.limit, args.conv)


if __name__ == "__main__":
    main()
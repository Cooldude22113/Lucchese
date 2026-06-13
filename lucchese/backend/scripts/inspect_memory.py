"""
scripts/inspect_memory.py
Manual ChromaDB inspection entrypoint (Rule 18: scripts call real modules).

Run from backend/ with the venv active. No server required.

Commands:
    python -m scripts.inspect_memory stats
    python -m scripts.inspect_memory sample [--col knowledge|facts|style|documents|summaries]
                                    [--tier TIER] [--source SOURCE]
                                    [--ontology ONT] [--routing done|pending|all]
                                    [--limit N] [--offset N]
    python -m scripts.inspect_memory search QUERY [--col COLLECTION|all] [--limit N]
    python -m scripts.inspect_memory live [--routing done|pending|all] [--limit N] [--conv CONV_ID]

Global flags:
    --log PATH   Write output to a UTF-8 file as well as the terminal.
"""

from __future__ import annotations

import argparse

from memory.collections.chroma_client import get_client
from memory.inspection.memory_dump import COLLECTIONS, cmd_sample
from memory.inspection.memory_search import cmd_search
from memory.inspection.memory_stats import cmd_stats
from memory.inspection.recall_debugger import cmd_live
from observability.log_context import enable_log


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect Lucchese ChromaDB memory entries.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--log", type=str, default=None, metavar="PATH",
                        help="Write output to a UTF-8 file as well as the terminal.")

    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("stats", help="Counts and routing/ontology/tier/source breakdowns.")

    sp = sub.add_parser("sample", help="Browse entries with optional filters.")
    sp.add_argument("--col", default="knowledge", choices=COLLECTIONS)
    sp.add_argument("--tier", help="Filter by primary_tier1")
    sp.add_argument("--source", help="Filter by source")
    sp.add_argument("--ontology", help="Filter by ontology class")
    sp.add_argument("--routing", choices=["done", "pending", "all"], default="all",
                    help="Routing status filter (knowledge only)")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--offset", type=int, default=0)

    ss = sub.add_parser("search", help="Semantic search and show matching entries.")
    ss.add_argument("query")
    ss.add_argument("--col", default="all", choices=COLLECTIONS + ["all"])
    ss.add_argument("--limit", type=int, default=5, help="Results per collection")

    sl = sub.add_parser("live", help="Recent live Lucchese ingestions, one per exchange.")
    sl.add_argument("--routing", choices=["done", "pending", "all"], default="all")
    sl.add_argument("--limit", type=int, default=20, help="Number of exchanges to show")
    sl.add_argument("--conv", help="Filter to a specific conv_id")

    args = parser.parse_args()

    if args.log:
        enable_log(args.log)

    if not args.cmd:
        parser.print_help()
        return

    client = get_client()

    if args.cmd == "stats":
        cmd_stats(client)
    elif args.cmd == "sample":
        cmd_sample(client, args.col, args.tier, args.source,
                   args.routing, args.ontology, args.limit, args.offset)
    elif args.cmd == "search":
        cmd_search(client, args.query, args.col, args.limit)
    elif args.cmd == "live":
        cmd_live(client, args.routing, args.limit, args.conv)


if __name__ == "__main__":
    main()

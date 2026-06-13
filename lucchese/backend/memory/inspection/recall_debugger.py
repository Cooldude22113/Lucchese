"""
memory/inspection/recall_debugger.py
Read-only view of recent live Lucchese ingestions, one entry per exchange (Rule 17).
"""

from __future__ import annotations

from memory.inspection.memory_dump import SEP, get_col


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

    seen: dict = {}
    for meta in results["metadatas"]:
        key = (meta.get("conv_id", ""), meta.get("pair_idx", ""))
        if key not in seen:
            seen[key] = meta

    exchanges = sorted(seen.values(), key=lambda m: m.get("created_at", ""), reverse=True)
    exchanges = exchanges[:limit]

    total_chunks = len(results["metadatas"])
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

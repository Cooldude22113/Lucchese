"""
memory/inspection/memory_search.py
Read-only semantic search across collections for inspection (Rule 17).
"""

from __future__ import annotations

from memory.inspection.memory_dump import COLLECTIONS, SEP, get_col, print_entry


def cmd_search(client, query, col_name, limit):
    cols_to_search = (
        [c for c in COLLECTIONS if c != "summaries"] if col_name == "all" else [col_name]
    )

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
            ids = results["ids"][0]
            docs = results["documents"][0]
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

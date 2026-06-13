"""
memory/inspection/memory_dump.py
Read-only browsing of ChromaDB entries (Rule 17).

Shared constants/helpers (COLLECTIONS, SEP, get_col, print_entry) plus the
filtered `sample` browser. Used by the inspect_memory script.
"""

from __future__ import annotations

COLLECTIONS = ["knowledge", "facts", "style", "documents", "summaries"]
SEP = "-" * 70


def get_col(client, name):
    """Return a collection by name, or None if it does not exist."""
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

    ids = results["ids"]
    docs = results["documents"]
    metas = results["metadatas"]
    total = col.count()

    filters_desc = "  ".join(filter(None, [
        f"tier={tier}" if tier else "",
        f"source={source}" if source else "",
        f"ontology={ontology}" if ontology else "",
        f"routing={routing}" if routing != "all" else "",
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

"""
ingest_grok.py
Parses your Grok export and loads it into ChromaDB with 3 collections:
  - knowledge   : full conversation chunks (searchable history)
  - facts       : auto-extracted user messages (what YOU said / asked)
  - style       : your writing style samples

Usage (from backend folder with venv active):
    python ingest_grok.py --input "C:\path\to\prod-grok-backend.json"
"""

import json
import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

# ── Config ──────────────────────────────────────────────────────────────────
CHROMA_PATH = "./chroma_db"
EMBED_MODEL  = "all-MiniLM-L6-v2"   # fast, good quality, runs locally
CHUNK_SIZE   = 800                   # characters per chunk
CHUNK_OVERLAP = 100

# ── ChromaDB setup ───────────────────────────────────────────────────────────
def get_client_and_ef():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL
    )
    return client, ef

# ── Helpers ──────────────────────────────────────────────────────────────────
def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += size - overlap
    return chunks

def parse_timestamp(ts) -> str:
    """Normalise various timestamp formats to ISO string."""
    if isinstance(ts, str):
        return ts
    if isinstance(ts, dict) and "$date" in ts:
        inner = ts["$date"]
        if isinstance(inner, dict) and "$numberLong" in inner:
            ms = int(inner["$numberLong"])
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
        if isinstance(inner, str):
            return inner
    return str(ts)

def is_user_message(sender: str) -> bool:
    return sender.lower() == "human"

# ── Parse conversations ───────────────────────────────────────────────────────
def parse_export(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    conversations = data.get("conversations", [])
    print(f"Found {len(conversations)} conversations")

    knowledge_docs = []   # full chunked conversations
    facts_docs     = []   # user messages only
    style_docs     = []   # user messages for style (longer ones only)

    for conv in conversations:
        meta   = conv.get("conversation", {})
        conv_id    = meta.get("id", "unknown")
        title      = meta.get("title", "Untitled")
        created    = meta.get("create_time", "")
        responses  = conv.get("responses", [])

        if not responses:
            continue

        # Build full conversation text
        turns = []
        user_messages = []

        for r in responses:
            resp   = r.get("response", {})
            sender = resp.get("sender", "unknown")
            msg    = resp.get("message", "") or ""
            ts     = parse_timestamp(resp.get("create_time", ""))

            if not msg.strip():
                continue

            label = "You" if is_user_message(sender) else "Grok"
            turns.append(f"[{label}]: {msg.strip()}")

            if is_user_message(sender) and len(msg.strip()) > 20:
                user_messages.append({
                    "text": msg.strip(),
                    "conv_id": conv_id,
                    "timestamp": ts,
                    "title": title,
                })

        if not turns:
            continue

        # ── knowledge collection: chunked full conversation ──
        full_text = f"Conversation: {title}\n\n" + "\n\n".join(turns)
        for i, chunk in enumerate(chunk_text(full_text)):
            knowledge_docs.append({
                "id":   f"know_{conv_id}_{i}",
                "text": chunk,
                "meta": {
                    "source":    "grok",
                    "conv_id":   conv_id,
                    "title":     title,
                    "created":   str(created),
                    "chunk_idx": str(i),
                    "type":      "knowledge",
                }
            })

        # ── facts collection: each user message ──
        for j, um in enumerate(user_messages):
            facts_docs.append({
                "id":   f"fact_{conv_id}_{j}",
                "text": um["text"],
                "meta": {
                    "source":    "grok",
                    "conv_id":   um["conv_id"],
                    "title":     um["title"],
                    "timestamp": str(um["timestamp"]),
                    "type":      "fact",
                }
            })

        # ── style collection: longer user messages (>80 chars) ──
        long_msgs = [um for um in user_messages if len(um["text"]) > 80]
        for k, um in enumerate(long_msgs):
            style_docs.append({
                "id":   f"style_{conv_id}_{k}",
                "text": um["text"],
                "meta": {
                    "source":    "grok",
                    "conv_id":   um["conv_id"],
                    "title":     um["title"],
                    "type":      "style",
                }
            })

    return knowledge_docs, facts_docs, style_docs

# ── Ingest into ChromaDB ──────────────────────────────────────────────────────
def ingest(docs, collection, batch_size=50):
    """Add docs to a ChromaDB collection in batches."""
    total = len(docs)
    print(f"  Ingesting {total} documents into '{collection.name}'...")

    for i in range(0, total, batch_size):
        batch = docs[i:i+batch_size]
        collection.upsert(
            ids        = [d["id"]   for d in batch],
            documents  = [d["text"] for d in batch],
            metadatas  = [d["meta"] for d in batch],
        )
        print(f"  [{collection.name}] {min(i+batch_size, total)}/{total}", end="\r")

    print(f"  [{collection.name}] Done — {total} docs loaded.        ")

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Ingest Grok export into ChromaDB")
    parser.add_argument("--input", required=True, help="Path to prod-grok-backend.json")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        return

    print(f"\nParsing {input_path.name}...")
    knowledge_docs, facts_docs, style_docs = parse_export(str(input_path))

    print(f"\nParsed:")
    print(f"  Knowledge chunks : {len(knowledge_docs)}")
    print(f"  Fact messages    : {len(facts_docs)}")
    print(f"  Style samples    : {len(style_docs)}")

    print(f"\nConnecting to ChromaDB at '{CHROMA_PATH}'...")
    client, ef = get_client_and_ef()

    col_knowledge = client.get_or_create_collection("knowledge", embedding_function=ef)
    col_facts     = client.get_or_create_collection("facts",     embedding_function=ef)
    col_style     = client.get_or_create_collection("style",     embedding_function=ef)

    print("\nIngesting — this may take a few minutes (embeddings are computed locally)...\n")
    ingest(knowledge_docs, col_knowledge)
    ingest(facts_docs,     col_facts)
    ingest(style_docs,     col_style)

    print("\n✓ All done! ChromaDB is ready at:", Path(CHROMA_PATH).resolve())
    print(f"  knowledge : {col_knowledge.count()} docs")
    print(f"  facts     : {col_facts.count()} docs")
    print(f"  style     : {col_style.count()} docs")

if __name__ == "__main__":
    main()

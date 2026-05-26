"""
ingest_grok.py
Parses your Grok export and loads it into ChromaDB with 3 collections:
  - knowledge   : full conversation chunks (user + grok together)
  - facts       : user messages only (what YOU said / asked)
  - style       : longer user messages for writing style reference

WHAT CHANGED FROM THE OLD VERSION:
- Knowledge stores full exchanges (user + grok) not just your messages
- Category set to 'general' at ingest — run reclassify.py after
- 50-char minimum for facts (was 20), 100-char for style (was 80)
- classify_memory removed entirely — reclassify.py handles this with Ollama

Usage (from backend folder with venv active):
    venv\Scripts\activate
    python ingest_grok.py --input "C:\path\to\prod-grok-backend.json"

To wipe existing Grok entries first:
    python ingest_grok.py --input "C:\path\to\prod-grok-backend.json" --wipe

Workflow:
    1. Run ingest_chatgpt.py --wipe
    2. Run ingest_grok.py --wipe
    3. Run reclassify.py
    4. Admin panel -> Manage -> Rebuild Summaries
"""

import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
import re

import chromadb
from chromadb.utils import embedding_functions

# ── Config ────────────────────────────────────────────────────────────────────
CHROMA_PATH   = "./chroma_db"
EMBED_MODEL   = "nomic-ai/nomic-embed-text-v1"
CHUNK_SIZE    = 800
CHUNK_OVERLAP = 100
MIN_FACT_LEN  = 50   # minimum chars for a user message to be stored as a fact
MIN_STYLE_LEN = 100  # minimum chars for a user message to be stored as a style sample

# ── ChromaDB setup ────────────────────────────────────────────────────────────
def get_client_and_ef():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL,
        trust_remote_code=True
    )
    return client, ef

# ── Text chunking ─────────────────────────────────────────────────────────────
def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks  = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= size:
            current = (current + " " + sentence).strip()
        else:
            if current:
                chunks.append(current)
            if len(sentence) > size:
                for i in range(0, len(sentence), size - overlap):
                    part = sentence[i:i + size]
                    if part.strip():
                        chunks.append(part.strip())
            else:
                current = sentence

    if current:
        chunks.append(current)

    return [c for c in chunks if c.strip()]

# ── Timestamp ─────────────────────────────────────────────────────────────────
def parse_timestamp(ts) -> str:
    """Normalise Grok's MongoDB-style timestamps to ISO string."""
    if isinstance(ts, str) and ts:
        return ts
    if isinstance(ts, dict) and "$date" in ts:
        inner = ts["$date"]
        if isinstance(inner, dict) and "$numberLong" in inner:
            ms = int(inner["$numberLong"])
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
        if isinstance(inner, str):
            return inner
    return ""

def is_user_message(sender: str) -> bool:
    return sender.lower() == "human"

# ── Wipe existing Grok entries ────────────────────────────────────────────────
def wipe_grok_entries(col_knowledge, col_facts, col_style):
    print("Wiping existing Grok entries...")
    for col in [col_knowledge, col_facts, col_style]:
        try:
            results = col.get(where={"source": "grok"})
            if results["ids"]:
                col.delete(ids=results["ids"])
                print(f"  Deleted {len(results['ids'])} entries from '{col.name}'")
            else:
                print(f"  Nothing to delete in '{col.name}'")
        except Exception as e:
            print(f"  Error wiping '{col.name}': {e}")

# ── Parse conversations ───────────────────────────────────────────────────────
def parse_export(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    conversations = data.get("conversations", [])
    print(f"Found {len(conversations)} conversations")

    knowledge_docs = []
    facts_docs     = []
    style_docs     = []
    skipped        = 0

    for conv in conversations:
        meta      = conv.get("conversation", {})
        conv_id   = meta.get("id", "unknown")
        title     = meta.get("title", "Untitled")
        created   = parse_timestamp(meta.get("create_time", ""))
        responses = conv.get("responses", [])

        if not responses:
            skipped += 1
            continue

        # ── Build full turn list (user + grok) ───────────────────────────────
        turns         = []
        user_messages = []

        for r in responses:
            resp   = r.get("response", {})
            sender = resp.get("sender", "unknown")
            msg    = resp.get("message", "") or ""
            ts     = parse_timestamp(resp.get("create_time", "")) or created

            if not msg.strip():
                continue

            label = "You" if is_user_message(sender) else "Grok"
            turns.append(f"[{label}]: {msg.strip()}")

            if is_user_message(sender):
                user_messages.append({
                    "text":       msg.strip(),
                    "conv_id":    conv_id,
                    "created_at": ts,
                    "title":      title,
                })

        if not turns:
            skipped += 1
            continue

        # ── knowledge: full exchanges (you + grok together) ──────────────────
        # Key fix from old version — Grok's responses are included so memory
        # has context when retrieved. Matches how main.py stores live chats.
        full_text = f"Conversation: {title}\n\n" + "\n\n".join(turns)
        for i, chunk in enumerate(chunk_text(full_text)):
            knowledge_docs.append({
                "id":   f"grok_know_{conv_id}_{i}",
                "text": chunk,
                "meta": {
                    "source":     "grok",
                    "conv_id":    conv_id,
                    "title":      title,
                    "created_at": created,
                    "chunk_idx":  str(i),
                    "type":       "knowledge",
                    "category":   "general",  # reclassify.py handles this after
                }
            })

        # ── facts: each user message individually ─────────────────────────────
        # 50-char minimum to filter noise like "ok", "yes", "can you..."
        for j, um in enumerate(user_messages):
            if len(um["text"]) >= MIN_FACT_LEN:
                facts_docs.append({
                    "id":   f"grok_fact_{conv_id}_{j}",
                    "text": um["text"],
                    "meta": {
                        "source":     "grok",
                        "conv_id":    um["conv_id"],
                        "title":      um["title"],
                        "created_at": um["created_at"],
                        "type":       "fact",
                        "category":   "general",  # reclassify.py handles this after
                    }
                })

        # ── style: longer user messages for writing style reference ───────────
        # 100-char minimum — only messages that show actual writing style
        for k, um in enumerate(user_messages):
            if len(um["text"]) >= MIN_STYLE_LEN:
                style_docs.append({
                    "id":   f"grok_style_{conv_id}_{k}",
                    "text": um["text"],
                    "meta": {
                        "source":     "grok",
                        "conv_id":    um["conv_id"],
                        "title":      um["title"],
                        "created_at": um["created_at"],
                        "type":       "style",
                        "category":   "general",  # reclassify.py handles this after
                    }
                })

    if skipped:
        print(f"  Skipped {skipped} empty/invalid conversations")

    return knowledge_docs, facts_docs, style_docs

# ── Ingest into ChromaDB ──────────────────────────────────────────────────────
def ingest(docs, collection, batch_size=50):
    total = len(docs)
    if total == 0:
        print(f"  No documents to ingest into '{collection.name}'")
        return
    print(f"  Ingesting {total} documents into '{collection.name}'...")
    for i in range(0, total, batch_size):
        batch = docs[i:i + batch_size]
        collection.upsert(
            ids       = [d["id"]   for d in batch],
            documents = [d["text"] for d in batch],
            metadatas = [d["meta"] for d in batch],
        )
        done = min(i + batch_size, total)
        print(f"  [{collection.name}] {done}/{total}", end="\r")
    print(f"  [{collection.name}] Done — {total} docs loaded.        ")

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Ingest Grok export into ChromaDB")
    parser.add_argument("--input", required=True, help="Path to prod-grok-backend.json")
    parser.add_argument("--wipe",  action="store_true", help="Wipe existing Grok entries before ingesting")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        return

    print(f"\nConnecting to ChromaDB at '{CHROMA_PATH}'...")
    client, ef    = get_client_and_ef()
    col_knowledge = client.get_or_create_collection("knowledge", embedding_function=ef)
    col_facts     = client.get_or_create_collection("facts",     embedding_function=ef)
    col_style     = client.get_or_create_collection("style",     embedding_function=ef)

    if args.wipe:
        wipe_grok_entries(col_knowledge, col_facts, col_style)

    print(f"\nParsing {input_path.name}...")
    knowledge_docs, facts_docs, style_docs = parse_export(str(input_path))

    print(f"\nParsed:")
    print(f"  Knowledge chunks : {len(knowledge_docs)}")
    print(f"  Fact messages    : {len(facts_docs)}")
    print(f"  Style samples    : {len(style_docs)}")

    print("\nIngesting — this may take a few minutes...\n")
    ingest(knowledge_docs, col_knowledge)
    ingest(facts_docs,     col_facts)
    ingest(style_docs,     col_style)

    print("\n✓ Done!")
    print(f"  knowledge : {col_knowledge.count()} total docs")
    print(f"  facts     : {col_facts.count()} total docs")
    print(f"  style     : {col_style.count()} total docs")
    print("\nNext step: run reclassify.py to classify all entries with Ollama")

if __name__ == "__main__":
    main()

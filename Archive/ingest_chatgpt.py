"""
ingest_chatgpt.py
Parses your ChatGPT export and loads it into ChromaDB.

WHAT CHANGED FROM THE OLD VERSION:
- Stores full exchanges (user + assistant together) not just user messages
- Facts and style still user-only, but with proper 50-char minimum
- Category set to 'general' at ingest — run reclassify.py after for LLM classification
- BFS uses deque instead of list (faster for large conversations)
- Multi-turn conversations stored as pairs for proper context

Usage (from backend folder with venv active):
    python ingest_chatgpt.py --input "C:\path\to\conversations-000.json"

To ingest all files at once (Windows — use PowerShell glob):
    python ingest_chatgpt.py --input "C:\path\to\conversations-000.json" "C:\path\to\conversations-001.json"

To wipe existing ChatGPT entries first:
    python ingest_chatgpt.py --input "C:\path\to\conversations-000.json" --wipe

Workflow:
    1. Run this script with --wipe to replace old data
    2. Run reclassify.py to classify all entries with Ollama
    3. In admin panel: Manage -> Rebuild Summaries
"""

import json
import argparse
import glob
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

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
    chunks = []
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
    if isinstance(ts, (int, float)) and ts > 0:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return ""

# ── Message extraction ────────────────────────────────────────────────────────
def extract_messages(mapping: dict) -> list:
    """
    Walk the ChatGPT mapping tree using BFS and extract messages in order.
    Uses deque for O(1) popleft instead of O(n) list.pop(0).
    Returns list of dicts with role, text, timestamp.
    Multi-modal parts (images, files) are skipped — text only.
    """
    # Find root node (no parent)
    root = None
    for node_id, node in mapping.items():
        if node.get('parent') is None:
            root = node_id
            break

    if not root:
        return []

    messages = []
    visited  = set()
    queue    = deque([root])

    while queue:
        node_id = queue.popleft()
        if node_id in visited:
            continue
        visited.add(node_id)

        node = mapping.get(node_id, {})
        msg  = node.get('message')

        if msg:
            role    = msg.get('author', {}).get('role', '')
            content = msg.get('content', {})
            parts   = content.get('parts', [])

            # Join string parts only — skip images, files, tool calls
            text = ' '.join([p for p in parts if isinstance(p, str)]).strip()
            ts   = parse_timestamp(msg.get('create_time'))

            if text and role in ('user', 'assistant'):
                messages.append({
                    'role':      role,
                    'text':      text,
                    'timestamp': ts,
                })

        queue.extend(node.get('children', []))

    return messages

# ── Build exchange pairs ───────────────────────────────────────────────────────
def build_exchange_pairs(messages: list) -> list:
    """
    Group messages into user+assistant pairs.
    Each pair captures the full context of an exchange.
    Returns list of dicts with user_text, assistant_text, timestamp.
    """
    pairs = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg['role'] == 'user':
            user_text = msg['text']
            user_ts   = msg['timestamp']
            # Look ahead for assistant reply
            assistant_text = ""
            if i + 1 < len(messages) and messages[i + 1]['role'] == 'assistant':
                assistant_text = messages[i + 1]['text']
                i += 1  # skip assistant on next iteration
            pairs.append({
                'user_text':      user_text,
                'assistant_text': assistant_text,
                'timestamp':      user_ts,
            })
        i += 1
    return pairs

# ── Parse conversations ────────────────────────────────────────────────────────
def parse_file(path: str):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not isinstance(data, list):
        print(f"  Unexpected format in {path} — expected a list of conversations")
        return [], [], []

    knowledge_docs = []
    facts_docs     = []
    style_docs     = []
    skipped        = 0

    for conv in data:
        conv_id = conv.get('id') or conv.get('conversation_id', 'unknown')
        title   = conv.get('title', 'Untitled')
        created = parse_timestamp(conv.get('create_time'))
        mapping = conv.get('mapping', {})

        if not mapping:
            skipped += 1
            continue

        messages = extract_messages(mapping)
        if not messages:
            skipped += 1
            continue

        pairs = build_exchange_pairs(messages)
        if not pairs:
            skipped += 1
            continue

        # ── knowledge: full exchanges (user + assistant) chunked together ──────
        # This is the key fix — assistant context is included so memory
        # makes sense when retrieved. Matches how main.py stores live chats.
        exchange_lines = []
        for p in pairs:
            if p['user_text']:
                exchange_lines.append(f"[You]: {p['user_text']}")
            if p['assistant_text']:
                exchange_lines.append(f"[ChatGPT]: {p['assistant_text']}")

        full_exchange = f"Conversation: {title}\n\n" + "\n\n".join(exchange_lines)

        for i, chunk in enumerate(chunk_text(full_exchange)):
            knowledge_docs.append({
                "id":   f"cgpt_know_{conv_id}_{i}",
                "text": chunk,
                "meta": {
                    "source":     "chatgpt",
                    "conv_id":    conv_id,
                    "title":      title,
                    "created_at": created,
                    "chunk_idx":  str(i),
                    "type":       "knowledge",
                    "category":   "general",  # reclassify.py handles this after
                }
            })

        # ── facts: each user message individually ─────────────────────────────
        # User messages only — these are statements of what Alex said/thinks/wants.
        # 50-char minimum to filter out noise like "ok", "yes", "thanks"
        for j, p in enumerate(pairs):
            user_text = p['user_text'].strip()
            if len(user_text) >= MIN_FACT_LEN:
                facts_docs.append({
                    "id":   f"cgpt_fact_{conv_id}_{j}",
                    "text": user_text,
                    "meta": {
                        "source":     "chatgpt",
                        "conv_id":    conv_id,
                        "title":      title,
                        "created_at": p['timestamp'] or created,
                        "type":       "fact",
                        "category":   "general",  # reclassify.py handles this after
                    }
                })

        # ── style: longer user messages for writing style reference ───────────
        # 100-char minimum — only messages long enough to show actual writing style
        for k, p in enumerate(pairs):
            user_text = p['user_text'].strip()
            if len(user_text) >= MIN_STYLE_LEN:
                style_docs.append({
                    "id":   f"cgpt_style_{conv_id}_{k}",
                    "text": user_text,
                    "meta": {
                        "source":     "chatgpt",
                        "conv_id":    conv_id,
                        "title":      title,
                        "created_at": p['timestamp'] or created,
                        "type":       "style",
                        "category":   "general",  # reclassify.py handles this after
                    }
                })

    if skipped:
        print(f"  Skipped {skipped} empty/invalid conversations")

    return knowledge_docs, facts_docs, style_docs

# ── Wipe existing ChatGPT entries ─────────────────────────────────────────────
def wipe_chatgpt_entries(col_knowledge, col_facts, col_style):
    print("Wiping existing ChatGPT entries...")
    for col in [col_knowledge, col_facts, col_style]:
        try:
            results = col.get(where={"source": "chatgpt"})
            if results["ids"]:
                col.delete(ids=results["ids"])
                print(f"  Deleted {len(results['ids'])} entries from '{col.name}'")
            else:
                print(f"  Nothing to delete in '{col.name}'")
        except Exception as e:
            print(f"  Error wiping '{col.name}': {e}")

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

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Ingest ChatGPT export into ChromaDB")
    parser.add_argument("--input", required=True, nargs="+", help="Path(s) to conversations-XXX.json files")
    parser.add_argument("--wipe",  action="store_true", help="Wipe existing ChatGPT entries before ingesting")
    args = parser.parse_args()

    # Expand any glob patterns
    input_files = []
    for pattern in args.input:
        expanded = glob.glob(pattern)
        if expanded:
            input_files.extend(expanded)
        else:
            input_files.append(pattern)

    input_files = sorted(set(input_files))
    print(f"\nFiles to process: {len(input_files)}")
    for f in input_files:
        print(f"  {f}")

    print(f"\nConnecting to ChromaDB at '{CHROMA_PATH}'...")
    client, ef    = get_client_and_ef()
    col_knowledge = client.get_or_create_collection("knowledge", embedding_function=ef)
    col_facts     = client.get_or_create_collection("facts",     embedding_function=ef)
    col_style     = client.get_or_create_collection("style",     embedding_function=ef)

    if args.wipe:
        wipe_chatgpt_entries(col_knowledge, col_facts, col_style)

    all_knowledge, all_facts, all_style = [], [], []

    for path in input_files:
        p = Path(path)
        if not p.exists():
            print(f"\nFile not found: {path}")
            continue
        print(f"\nParsing {p.name}...")
        k, f, s = parse_file(str(p))
        all_knowledge.extend(k)
        all_facts.extend(f)
        all_style.extend(s)
        print(f"  Knowledge: {len(k)} | Facts: {len(f)} | Style: {len(s)}")

    print(f"\nTotal parsed:")
    print(f"  Knowledge chunks : {len(all_knowledge)}")
    print(f"  Fact messages    : {len(all_facts)}")
    print(f"  Style samples    : {len(all_style)}")

    print("\nIngesting — this may take several minutes...\n")
    ingest(all_knowledge, col_knowledge)
    ingest(all_facts,     col_facts)
    ingest(all_style,     col_style)

    print("\n✓ Done!")
    print(f"  knowledge : {col_knowledge.count()} total docs")
    print(f"  facts     : {col_facts.count()} total docs")
    print(f"  style     : {col_style.count()} total docs")
    print("\nNext step: run reclassify.py to classify all entries with Ollama")

if __name__ == "__main__":
    main()

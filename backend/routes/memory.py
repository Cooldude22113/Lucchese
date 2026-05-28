"""
memory.py
All ChromaDB memory operations for Lucchese.
Handles: classification, ingestion, deduplication, search, query expansion, memory commands.
"""

import re
import uuid
import math
import httpx
from datetime import datetime, timezone
from sentence_transformers import CrossEncoder
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
import os
import logging
load_dotenv()

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
EMBED_MODEL   = "nomic-ai/nomic-embed-text-v1"
CHUNK_SIZE    = 800
CHUNK_OVERLAP = 100

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/api/chat"
MODEL_FAST = os.getenv("MODEL_FAST", "gemma2:27b")

SIMILARITY_THRESHOLD = 0.25  # L2 distance — lower = stricter dedup

# Recency bonus applied to cross-encoder scores. Tune this constant to
# shift the balance between semantic relevance and recency.
RECENCY_WEIGHT = 0.1

# ── ChromaDB setup ────────────────────────────────────────────────────────────
ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name=EMBED_MODEL,
    trust_remote_code=True
)
chroma = chromadb.PersistentClient(path=CHROMA_PATH)

col_knowledge = chroma.get_or_create_collection("knowledge", embedding_function=ef)
col_facts     = chroma.get_or_create_collection("facts",     embedding_function=ef)
col_style     = chroma.get_or_create_collection("style",     embedding_function=ef)
col_documents = chroma.get_or_create_collection("documents", embedding_function=ef)
col_summaries = chroma.get_or_create_collection("summaries", embedding_function=ef)

# ── Reranker ──────────────────────────────────────────────────────────────────
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

# ── Categories ────────────────────────────────────────────────────────────────
CATEGORIES = [
    "ptpreps", "coaching", "fitness", "food", "cooking", "health",
    "compounds", "supplements_nootropics", "psychedelics", "property",
    "finance", "money", "lucchese", "tech", "security", "ai", "hardware",
    "content", "music", "media_gaming", "psychology", "mindset",
    "neuroscience", "social_dynamics", "family", "relationships", "travel",
    "spirituality", "conspiracy", "religion_esoteric", "philosophy",
    "politics", "economics", "history_culture", "science", "mental_health",
    "career", "pub", "general"
]

CATEGORY_LIST = ", ".join(CATEGORIES)

# ── Text chunking ─────────────────────────────────────────────────────────────
def chunk_text(text: str) -> list[str]:
    # Split on sentence boundaries first
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= CHUNK_SIZE:
            current = (current + " " + sentence).strip()
        else:
            if current:
                chunks.append(current)
            # If a single sentence exceeds chunk size, split it hard
            if len(sentence) > CHUNK_SIZE:
                for i in range(0, len(sentence), CHUNK_SIZE - CHUNK_OVERLAP):
                    part = sentence[i:i + CHUNK_SIZE]
                    if part.strip():
                        chunks.append(part.strip())
            else:
                current = sentence

    if current:
        chunks.append(current)

    return [c for c in chunks if c.strip()]


# ── Deduplication ─────────────────────────────────────────────────────────────
def is_duplicate_memory(text: str, collection, n: int = 1) -> bool:
    """Returns True if a very similar chunk already exists in the collection."""
    try:
        results = collection.query(query_texts=[text], n_results=n, include=["distances"])
        if results["distances"] and results["distances"][0]:
            closest_distance = results["distances"][0][0]
            return closest_distance < SIMILARITY_THRESHOLD
    except Exception as e:
        logger.warning("is_duplicate_memory check failed: %s — allowing write", e)
    return False

# ── Classification ────────────────────────────────────────────────────────────
async def classify_memory(text: str) -> str:
    """
    Classify a memory chunk using the local Ollama model.
    Fast, private, no API calls. Falls back to general if model fails.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_FAST,
                    "messages": [{
                        "role": "user",
                        "content": f"""Classify this text into exactly one category. Reply with only the category name, nothing else, no punctuation, no explanation.

Categories: {CATEGORY_LIST}

Text: {text[:500]}

Category:"""
                    }],
                    "stream": False,
                    "options": {
                        "temperature": 0,
                        "num_predict": 10,
                    }
                }
            )
            result = res.json()["message"]["content"].strip().lower()
            result = result.split()[0].strip(".,\n")
            return result if result in CATEGORIES else "general"
    except Exception as e:
        print(f"classify_memory error: {e}")
        return "general"

# ── Memory quality filter ─────────────────────────────────────────────────────
def should_ingest(user_msg: str, assistant_reply: str) -> bool:
    msg = user_msg.lower().strip()

    if len(msg) < 30:
        return False

    uncertainty = ["i don't know", "i'm not sure", "i can't find", "i don't have"]
    if any(p in assistant_reply.lower() for p in uncertainty):
        return False

    signals = [
        "my ", "i am", "i'm", "we ", "i have", "i've", "i do", "i don't",
        "alex", "ptpreps", "prefer", "always", "never", "usually", "hate",
        "love", "want", "need", "goal", "plan", "think", "believe", "feel"
    ]
    if any(w in msg for w in signals):
        return True

    return False

def _strip_preamble(text: str, min_words: int = 12) -> str:
    """Strip short preamble sentences from assistant responses."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    for i, s in enumerate(sentences):
        if len(s.split()) >= min_words:
            return " ".join(sentences[i:])
    return text


# ── Ingestion ─────────────────────────────────────────────────────────────────
async def ingest_exchange(conversation_id: str, user_msg: str, assistant_reply: str):
    """
    Store a live Lucchese exchange in ChromaDB.
 
    Schema now matches ingest_chatgpt_v9.py / ingest_grok_v2.py:
      - Document: user_msg only (no assistant text contamination)
      - user_text_raw: clean user message in metadata
      - assistant_excerpt: 600 chars, preamble-stripped
      - routing_done: "false" — reclassify.py will classify this
      - pair_idx: unique per exchange for grouping by reclassify
 
    Facts and style still created immediately for live session use.
    Reclassify will also route these with LLM accuracy on the next run,
    producing higher-quality routing than the length-based threshold here.
    """
    now       = datetime.now(timezone.utc).isoformat()
    pair_idx  = uuid.uuid4().hex[:8]
    user_text = user_msg.strip()
 
    if not user_text:
        return
 
    assistant_excerpt = _strip_preamble(assistant_reply)[:600]
    assistant_length  = len(assistant_reply)
 
    base_meta = {
        "source":            "lucchese",
        "conv_id":           conversation_id,
        "pair_idx":          pair_idx,
        "type":              "knowledge",
        "created_at":        now,
        # User text stored clean in metadata — document field is for embedding
        "user_text_raw":     user_text,
        "assistant_excerpt": assistant_excerpt,
        "assistant_length":  assistant_length,
        # Classification deferred to reclassify.py
        "category":          "unclassified",
        "ontology":          "unclassified",
        "source_type":       "unclassified",
        "primary_tier1":     "unclassified",
        "primary_tier2":     "unclassified",
        "primary_tier3":     "unclassified",
        "secondary_tier1":   "",
        "secondary_tier2":   "",
        "secondary_tier3":   "",
        "is_personal":       "unclassified",
        "engagement":        "unclassified",
        "routing_done":      "false",
    }
 
    # Embed user_text only — assistant text caused embedding contamination
    for i, chunk in enumerate(chunk_text(user_text)):
        if not is_duplicate_memory(chunk, col_knowledge):
            col_knowledge.upsert(
                ids       = [f"lucchese_{conversation_id}_{pair_idx}_{i}"],
                documents = [chunk],
                metadatas = [{**base_meta, "chunk_idx": str(i)}],
            )
 
    # Facts — use should_ingest() for intent check, not raw length threshold.
    # Old threshold (> 20 chars) stored "ok" and "yes" as facts.
    if len(user_text) >= 50 and should_ingest(user_text, assistant_reply):
        if not is_duplicate_memory(user_text, col_facts):
            col_facts.upsert(
                ids       = [f"lucchese_fact_{conversation_id}_{pair_idx}"],
                documents = [user_text],
                metadatas = [{
                    **base_meta,
                    "type":                "fact",
                    "source_knowledge_id": f"lucchese_{conversation_id}_{pair_idx}_0",
                }],
            )
 
    # Style — keep 100 char minimum, only substantive messages
    if len(user_text) >= 100:
        if not is_duplicate_memory(user_text, col_style):
            col_style.upsert(
                ids       = [f"lucchese_style_{conversation_id}_{pair_idx}"],
                documents = [user_text],
                metadatas = [{
                    **base_meta,
                    "type":                "style",
                    "source_knowledge_id": f"lucchese_{conversation_id}_{pair_idx}_0",
                }],
            )

def ingest_document(doc_id: str, filename: str, text: str) -> int:
    chunks = chunk_text(text)
    now = datetime.now(timezone.utc).isoformat()

    for i, chunk in enumerate(chunks):
        col_documents.upsert(
            ids       = [f"doc_{doc_id}_chunk_{i}"],
            documents = [chunk],
            metadatas = [{
                "source":     "document",
                "doc_id":     doc_id,
                "filename":   filename,
                "chunk_idx":  str(i),
                "created_at": now,
            }]
        )

    return len(chunks)

# ── Query expansion ───────────────────────────────────────────────────────────
async def expand_query(query: str) -> list[str]:
    """
    Generate alternative phrasings of the query to improve retrieval coverage.
    Returns the original query plus up to 2 expansions.
    Falls back to just the original if the model call fails.
    """
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_FAST,
                    "messages": [{
                        "role": "user",
                        "content": f"""Rewrite this search query in 2 different ways to help find relevant memories.
Each rephrasing should approach the same topic from a different angle.
Reply with exactly 2 lines, one rephrasing per line, nothing else, no numbering, no explanation.

Query: {query}

Rephrasings:"""
                    }],
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 60,
                    }
                }
            )
            res.raise_for_status()
            data = res.json()

            if "message" not in data or "content" not in data["message"]:
                print(f"expand_query bad response: {data}")
                return [query]

            lines = data["message"]["content"].strip().split("\n")
            expansions = [l.strip() for l in lines if l.strip()][:2]
            return [query] + expansions
    except Exception as e:
        logger.error("expand_query error: %s", e)
        return [query]

# ── Search ────────────────────────────────────────────────────────────────────
async def search_memory(query: str, n: int = 5) -> str:
    """
    1. Pull summaries for relevant categories
    2. Expand query into multiple phrasings
    3. Pull candidate chunks from all collections
    4. Rerank with cross-encoder
    5. Return top deduplicated results
    """
    candidates = []
    now_ts = datetime.now(timezone.utc).timestamp()

    # ── Step 1: Pull relevant summaries ──────────────────────────────────────
    try:
        summary_hits = col_summaries.query(
            query_texts=[query],
            n_results=3,
            include=["documents", "distances", "metadatas"]
        )
        for doc, dist, meta in zip(
            summary_hits["documents"][0],
            summary_hits["distances"][0],
            summary_hits["metadatas"][0]
        ):
            if not doc.strip():
                continue
            relevance = 1 / (1 + dist)
            if relevance > 0.3:
                candidates.append((
                    relevance * 1.4,
                    f"Summary ({meta.get('category', 'general')})",
                    doc.strip()
                ))
    except Exception as e:
        logger.error("Summary search error: %s", e)

    # ── Step 2: Expand query and pull chunks ──────────────────────────────────
    queries    = await expand_query(query)
    raw_chunks = []
    seen_docs  = set()

    for col, label in [
        (col_knowledge, "Past conversation"),
        (col_facts,     "Things you've said"),
        (col_style,     "Your writing style"),
        (col_documents, "Your documents"),
    ]:
        try:
            for q in queries:
                hits = col.query(
                    query_texts=[q],
                    n_results=n * 2,
                    include=["documents", "distances", "metadatas"]
                )
                for doc, dist, meta in zip(
                    hits["documents"][0],
                    hits["distances"][0],
                    hits["metadatas"][0]
                ):
                    if not doc.strip():
                        continue
                    doc_key = doc[:100]
                    if doc_key in seen_docs:
                        continue
                    seen_docs.add(doc_key)

                    try:
                        created_ts = datetime.fromisoformat(meta.get("created_at", "")).timestamp()
                        age_days   = (now_ts - created_ts) / 86400
                        recency    = math.exp(-age_days / 365)
                    except Exception:
                        recency = 0.5

                    display_text = doc.strip()
                    if label == "Past conversation" and meta.get("user_text_raw"):
                        assistant_exc = meta.get("assistant_excerpt", "")
                        display_text  = meta["user_text_raw"].strip()
                        if assistant_exc:
                            display_text += f"\n→ {assistant_exc[:200]}"

                    raw_chunks.append({
                        "label":   label,
                        "doc":     display_text,
                        "recency": recency,
                        "is_fact": label == "Things you've said",
                    })
        except Exception as e:
            print(f"search_memory error ({label}): {e}")

    # ── Step 3: Rerank with cross-encoder ─────────────────────────────────────
    if raw_chunks:
        try:
            pairs  = [(query, c["doc"]) for c in raw_chunks]
            scores = reranker.predict(pairs)
            for chunk, score in zip(raw_chunks, scores):
                recency_bonus = chunk["recency"] * RECENCY_WEIGHT
                fact_bonus    = 0.05 if chunk["is_fact"] else 0.0
                final_score   = float(score) + recency_bonus + fact_bonus
                candidates.append((final_score, chunk["label"], chunk["doc"]))
        except Exception as e:
            print(f"Reranker error: {e}")
            for chunk in raw_chunks:
                candidates.append((chunk["recency"], chunk["label"], chunk["doc"]))

    # ── Step 4: Sort, deduplicate, return ─────────────────────────────────────
    candidates.sort(key=lambda x: x[0], reverse=True)

    seen = set()
    top  = []
    for score, label, doc in candidates:
        key = doc[:100]
        if key in seen:
            continue
        seen.add(key)
        top.append((label, doc))
        if len(top) >= 10:
            break

    if not top:
        return ""

    return "\n\n".join(f"[{label}]: {doc}" for label, doc in top)

# ── Memory commands ───────────────────────────────────────────────────────────
REMEMBER_PATTERNS = [
    r'\bremember that\b(.+)',
    r'\bremember:\b(.+)',
    r'\bsave this\b(.+)',
    r'\bstore this\b(.+)',
    r'\bnote that\b(.+)',
]

FORGET_PATTERNS = [
    r'\bforget that\b(.+)',
    r'\bforget\b (.+)',
    r'\bdelete that\b',
    r'\bunremember\b(.+)',
    r'\bremove that\b',
]

def detect_memory_command(message: str):
    """Returns ('remember', text), ('forget', text), or (None, None)"""
    msg = message.lower().strip()

    for pattern in REMEMBER_PATTERNS:
        match = re.search(pattern, msg)
        if match:
            return ("remember", match.group(1).strip())

    for pattern in FORGET_PATTERNS:
        match = re.search(pattern, msg)
        if match:
            content = match.group(1).strip() if match.lastindex else ""
            return ("forget", content)

    return (None, None)

async def handle_memory_command(command: str, content: str, conversation_id: str) -> str:
    now = datetime.now(timezone.utc).isoformat()

    if command == "remember":
        if not is_duplicate_memory(content, col_facts):
            col_facts.upsert(
                ids       = [f"explicit_fact_{uuid.uuid4().hex[:8]}"],
                documents = [content],
                metadatas = [{
                    "source":     "explicit",
                    "conv_id":    conversation_id,
                    "type":       "fact",
                    "category":   await classify_memory(content),
                    "created_at": now,
                }]
            )
            return f"Got it, I'll remember that: *{content}*"
        else:
            return "I already have that stored."

    elif command == "forget":
        deleted = 0
        if content:
            for col in [col_facts, col_knowledge, col_style]:
                try:
                    results = col.query(
                        query_texts=[content],
                        n_results=3,
                        include=["distances"]
                    )
                    if results["ids"] and results["ids"][0]:
                        for id_, dist in zip(results["ids"][0], results["distances"][0]):
                            if dist < 0.3:
                                col.delete(ids=[id_])
                                deleted += 1
                except Exception:
                    pass

        if deleted:
            return "Done, I've removed that from my memory."
        else:
            return "I couldn't find anything close enough to that in my memory to remove."
"""
ingest_grok.py
Parses your Grok export and loads it into ChromaDB with 3 collections:
  - knowledge   : full conversation chunks (searchable history)
  - facts       : auto-extracted user messages (what YOU said / asked)
  - style       : your writing style samples

Usage (from backend folder with venv active):
    python ingest_grok.py --input "C:\path\to\prod-grok-backend.json"

To wipe existing Grok entries first, add --wipe:
    python ingest_grok.py --input "C:\path\to\prod-grok-backend.json" --wipe
"""

import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
import re

import chromadb
from chromadb.utils import embedding_functions

# ── Config ──────────────────────────────────────────────────────────────────
CHROMA_PATH   = "./chroma_db"
EMBED_MODEL   = "all-MiniLM-L6-v2"
CHUNK_SIZE    = 800
CHUNK_OVERLAP = 100

# ── ChromaDB setup ───────────────────────────────────────────────────────────
def get_client_and_ef():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL
    )
    return client, ef

# ── Helpers ──────────────────────────────────────────────────────────────────
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
    return ""

def is_user_message(sender: str) -> bool:
    return sender.lower() == "human"

def classify_memory(text: str) -> str:
    t = text.lower()

    # ── PTPreps Business ──────────────────────────────────────────────────────
    if any(w in t for w in ['ptpreps', 'pt preps', 'meal prep business', 'subscription', 'shopify', 'appstle', 'allergen label', 'delivery checker', 'bundle', 'cook plan', 'fulfilment', 'dispatch', 'packaging', 'refund', 'allergen', 'haccp', 'food safety', 'food cooling', 'allergen listing']):
        return 'ptpreps'

    # ── Personal Training & Coaching ──────────────────────────────────────────
    if any(w in t for w in ['pt client', 'personal training', 'coaching client', 'programme card', 'check in', 'l3', 'level 3', 'practical assessment', 'smart goal', 'pt course', 'puregym assessment', 'phil feedback']):
        return 'coaching'

    # ── Fitness & Training ────────────────────────────────────────────────────
    if any(w in t for w in ['gym', 'workout', 'training', 'bodybuilding', 'lift', 'squat', 'deadlift', 'bench', 'cardio', 'mma', 'bjj', 'boxing', 'sparring', 'martial', 'cut', 'bulk', 'physique', 'looksmaxxing', 'mind muscle', 'shin splint', 'grip strength', 'leg day', 'resistance band', 'smelling salt']):
        return 'fitness'

    # ── Food & Recipes ────────────────────────────────────────────────────────
    if any(w in t for w in ['recipe', 'macro', 'protein', 'kcal', 'calorie', 'ingredient', 'menu', 'portion', 'bulking recipe', 'standard recipe', 'meal plan', 'nutrition', 'food diary', 'raw weight', 'cook weight']):
        return 'food'

    if any(w in t for w in ['cook', 'bake', 'roast', 'fry', 'sauté', 'braise', 'cuisine', 'kitchen', 'chef', 'jerk chicken', 'beef bourguignon', 'venison', 'sourdough', 'tallow', 'gastro']):
        return 'cooking'

    # ── Health & Body ─────────────────────────────────────────────────────────
    if any(w in t for w in ['health', 'cholesterol', 'sleep', 'injury', 'recovery', 'blood test', 'seizure', 'epilepsy', 'pain', 'doctor', 'nhs', 'medication', 'levetiracetam', 'pip', 'fit note', 'universal credit', 'deviated septum', 'jaw', 'chest spasm', 'vape', 'vaping', 'nicotine', 'cpap', 'sleep apnea', 'uars', 'daylight saving', 'circadian']):
        return 'health'

    # ── Compounds, PEDs & Peptides ────────────────────────────────────────────
    if any(w in t for w in ['trt', 'testosterone', 'test e', 'test enanthate', 'deca', 'eq ', 'equipoise', 'hcg', 'aromatase', 'estrogen', 'steroid', 'sarm', 'peptide', 'bpc', 'bpc-157', 'tb-500', 'glute injection', 'methylene blue', 'epo', 'armodafinil', 'modafinil']):
        return 'compounds'

    if any(w in t for w in ['supplement', 'creatine', 'vitamin', 'omega', 'magnesium', 'zinc', 'pre workout', 'whey', 'collagen', 'semax', 'selank', 'nootropic', 'paul stamets', 'microdosing', 'lsd', 'mushroom stack', 'caffeine', 'l-theanine', 'nlp', 'cognitive']):
        return 'supplements_nootropics'

    # ── Psychedelics & Altered States ─────────────────────────────────────────
    if any(w in t for w in ['psilocybin', 'mushroom', 'shroom', 'mycelium', 'grow kit', 'fungi', 'dmt', 'ayahuasca', 'sensory deprivation', 'float tank', 'cannabis', 'weed', 'cocaine', 'drug', 'addiction', 'withdrawal', 'perception', 'altered state']):
        return 'psychedelics'

    # ── Property & Real Estate ────────────────────────────────────────────────
    if any(w in t for w in ['property', 'mortgage', 'equity', 'tenant', 'hmo', 'landlord', 'brrr', 'r2r', 'yield', 'bridging', 'remortgage', 'estate agent', 'conveyancer', 'sdlt', 'rent to rent', 'deal analysis', 'analyse deal']):
        return 'property'

    # ── Finance & Money ───────────────────────────────────────────────────────
    if any(w in t for w in ['invest', 'stock', 'share', 'crypto', 'bitcoin', 'portfolio', 'dividend', 'index fund', 'isa', 'pension', 'compound interest', 'asset', 'holding company', 'family investment', 'financial literacy', 'economy', 'wealth']):
        return 'finance'

    if any(w in t for w in ['budget', 'spend', 'afford', 'debt', 'loan', 'cash flow', 'salary', 'invoice', 'tax', 'hmrc', 'self assessment', 'ltd company', 'sole trader', 'revolut', 'payroll', 'director pay', 'universal credit']):
        return 'money'

    # ── Tech & Building ───────────────────────────────────────────────────────
    if any(w in t for w in ['chroma', 'ollama', 'embeddings', 'rag', 'vector', 'building lucchese', 'lucchese feature', 'lucchese bug', 'lucchese memory', 'lucchese db', 'ai dashboard', 'ingest']):
        return 'lucchese'

    if any(w in t for w in ['code', 'python', 'javascript', 'react', 'fastapi', 'api', 'backend', 'frontend', 'debug', 'server', 'deploy', 'vite', 'database', 'sqlite', 'github', 'npm', 'venv', 'flask', 'ngrok', 'uvicorn']):
        return 'tech'

    if any(w in t for w in ['hack', 'pentest', 'security', 'xss', 'recon', 'ctf', 'exploit', 'cyber', 'vulnvault', 'osint', 'phishing', 'bug bounty', 'threat intel', 'kali']):
        return 'security'

    if any(w in t for w in ['ai model', 'gpt', 'claude', 'llm', 'prompt', 'machine learning', 'automation', 'chatgpt', 'grok', 'hallucination']):
        return 'ai'

    if any(w in t for w in ['pc build', 'gpu', 'cpu', 'psu', 'nzxt', 'radiator', 'liquid cooler', 'monitor', 'arduino', 'elegoo', 'mini pc', 'usb', 'coaxial', 'daisy chain']):
        return 'hardware'

    # ── Content & Creative ────────────────────────────────────────────────────
    if any(w in t for w in ['reel', 'youtube', 'tiktok', 'instagram', 'video edit', 'short form', 'thumbnail', 'caption', 'viral', 'content creator', '60 second']):
        return 'content'

    if any(w in t for w in ['music', 'song', 'track', 'dj', 'vinyl', 'beat', 'produce', 'guitar', 'drum', 'playlist', 'album', 'artist', 'songwriting', 'mandolin', 'pas rudiment', 'warner classics']):
        return 'music'

    if any(w in t for w in ['film', 'movie', 'series', 'netflix', 'documentary', 'episode', 'rdr2', 'minecraft', 'gaming', 'console', 'playstation', 'xbox', 'steam', 'gta', 'bg3']):
        return 'media_gaming'

    # ── Psychology & Mind ─────────────────────────────────────────────────────
    if any(w in t for w in ['psychology', 'psychopathy', 'narcissism', 'trauma', 'attachment', 'ego', 'shadow', 'identity', 'subconscious', 'behaviour', 'habit', 'addiction cycle', 'breaking the cycle', 'family enmeshment', 'boundaries', 'parenting yourself', 'inner child']):
        return 'psychology'

    if any(w in t for w in ['mindset', 'discipline', 'motivation', 'self improvement', 'stoic', 'focus', 'productivity', 'confidence', 'resilience', 'procrastination', 'resistance', 'momentum', 'consistency', 'insanity vs consistency']):
        return 'mindset'

    if any(w in t for w in ['neuroscience', 'neuroplasticity', 'dopamine', 'serotonin', 'neuromelanin', 'nervous system', 'brain', 'neurology', 'cognitive', 'consciousness', 'layers of consciousness', 'mind muscle']):
        return 'neuroscience'

    if any(w in t for w in ['nlp', 'attraction', 'masculine', 'feminine', 'dating', 'relationship', 'social dynamics', 'gym talk', 'gym convo', 'social tension', 'nice guys', 'manosphere']):
        return 'social_dynamics'

    # ── Family & Personal ─────────────────────────────────────────────────────
    if any(w in t for w in ['mum', 'dad', 'brother', 'sister', 'aunt', 'uncle', 'family', 'parent', 'grandma', 'grandad', 'nan', 'siblings', 'family conflict', 'family chaos', 'family pressure']):
        return 'family'

    if any(w in t for w in ['friend', 'mate', 'lad', 'social', 'night out', 'energy audit', 'friendships', 'protecting energy']):
        return 'relationships'

    if any(w in t for w in ['travel', 'holiday', 'flight', 'hotel', 'abroad', 'country', 'city', 'trip', 'amazon adventure', 'fishing']):
        return 'travel'

    # ── Spirituality & Esoteric ───────────────────────────────────────────────
    if any(w in t for w in ['consciousness', 'simulation', 'spiritual', 'universe', 'frequency', 'ancient', 'dimension', 'mandela effect', 'pyramid', 'parallel universe', 'quantum', 'double slit', 'superposition', 'dmt burning bush', 'heaven', 'hell', 'ascension', 'astral']):
        return 'spirituality'

    if any(w in t for w in ['conspiracy', 'deep state', 'adrenochrome', 'epstein', 'diddy', 'cia', 'isis cia', 'hearst hemp', 'flat earth', 'bob lazar', 'greer', 'ufo', 'alien', 'buga sphere', 'giants', 'dinosaur hoax', 'soros', 'sumitomo']):
        return 'conspiracy'

    if any(w in t for w in ['god', 'faith', 'religion', 'church', 'belief', 'bible', 'jesus', 'muslim', 'christian', 'jewish', 'quran', 'fallen angel', 'esau', 'ptah', 'egypt', 'freemason', 'satanism', 'antichrist', 'black magic', 'immortality key', 'psychedelic religion']):
        return 'religion_esoteric'

    if any(w in t for w in ['philosophy', 'meaning', 'purpose', 'existence', 'free will', 'morality', 'ethics', 'truth', 'simulation theory', 'devil hypothetical', 'your prophecy']):
        return 'philosophy'

    # ── World & Society ───────────────────────────────────────────────────────
    if any(w in t for w in ['politic', 'government', 'vote', 'election', 'law', 'immigration', 'war', 'policy', 'tommy robinson', 'israel', 'palestine', 'zionism', 'anti-semitism', 'green party', 'getting into politics', 'uk demographics']):
        return 'politics'

    if any(w in t for w in ['economy', 'inflation', 'central bank', 'money printing', 'nationalise', 'capitalism', 'decentralised', 'digital currency', 'global tension', 'world leadership', 'cultural extreme']):
        return 'economics'

    if any(w in t for w in ['history', 'civilisation', 'empire', 'ancient egypt', 'pyramids', 'solzhenitsyn', 'george washington', 'freddie mercury', 'elon musk', 'dan pena', 'paul allen', 'theo von', 'louis theroux', 'bob marley']):
        return 'history_culture'

    if any(w in t for w in ['science', 'physics', 'biology', 'chemistry', 'comet', 'ice age', 'asteroid', 'light pollution', 'sky', 'quantum', 'seed oil', 'cholesterol debate']):
        return 'science'

    if any(w in t for w in ['autism', 'schizophrenia', 'epilepsy awareness', 'mental health', 'self loathing', 'anger', 'overthinking', 'breaking free', 'stuck', 'chaos', 'life direction', 'reset', 'getting back on track']):
        return 'mental_health'

    # ── Career & Study ────────────────────────────────────────────────────────
    if any(w in t for w in ['job', 'recruit', 'hire', 'salary', 'career', 'interview', 'cv', 'comptia', 'it cert', 'microsoft 365', 'it support', 'it role']):
        return 'career'

    return 'general'

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

    for conv in conversations:
        meta      = conv.get("conversation", {})
        conv_id   = meta.get("id", "unknown")
        title     = meta.get("title", "Untitled")
        created   = meta.get("create_time", "")
        responses = conv.get("responses", [])

        if not responses:
            continue

        turns         = []
        user_messages = []

        for r in responses:
            resp   = r.get("response", {})
            sender = resp.get("sender", "unknown")
            msg    = resp.get("message", "") or ""
            # Use response timestamp if available, fall back to conversation timestamp
            ts = parse_timestamp(resp.get("create_time", "")) or str(created)

            if not msg.strip():
                continue

            label = "You" if is_user_message(sender) else "Grok"
            turns.append(f"[{label}]: {msg.strip()}")

            if is_user_message(sender) and len(msg.strip()) > 20:
                user_messages.append({
                    "text":      msg.strip(),
                    "conv_id":   conv_id,
                    "created_at": ts,  # ← correct key for search_memory
                    "title":     title,
                })

        if not turns:
            continue

        # ── knowledge: only YOUR turns, not Grok's responses ──
        user_turns = [t for t in turns if t.startswith("[You]:")]
        if not user_turns:
            continue
        full_text = f"Conversation: {title}\n\n" + "\n\n".join(user_turns)
        for i, chunk in enumerate(chunk_text(full_text)):
            knowledge_docs.append({
                "id":   f"know_{conv_id}_{i}",
                "text": chunk,
                "meta": {
                    "source":     "grok",
                    "conv_id":    conv_id,
                    "title":      title,
                    "created_at": str(created),  # ← correct key
                    "chunk_idx":  str(i),
                    "type":       "knowledge",
                    "category":   classify_memory(chunk),
                }
            })

        # ── facts: each user message ──
        for j, um in enumerate(user_messages):
            facts_docs.append({
                "id":   f"fact_{conv_id}_{j}",
                "text": um["text"],
                "meta": {
                    "source":     "grok",
                    "conv_id":    um["conv_id"],
                    "title":      um["title"],
                    "created_at": um["created_at"],  # ← correct key
                    "type":       "fact",
                    "category":   classify_memory(um["text"]),
                }
            })

        # ── style: longer user messages ──
        for k, um in enumerate([m for m in user_messages if len(m["text"]) > 80]):
            style_docs.append({
                "id":   f"style_{conv_id}_{k}",
                "text": um["text"],
                "meta": {
                    "source":     "grok",
                    "conv_id":    um["conv_id"],
                    "title":      um["title"],
                    "created_at": um["created_at"],  # ← correct key
                    "type":       "style",
                    "category":   classify_memory(um["text"]),
                }
            })

    return knowledge_docs, facts_docs, style_docs

# ── Ingest into ChromaDB ──────────────────────────────────────────────────────
def ingest(docs, collection, batch_size=50):
    total = len(docs)
    print(f"  Ingesting {total} documents into '{collection.name}'...")
    for i in range(0, total, batch_size):
        batch = docs[i:i + batch_size]
        collection.upsert(
            ids       = [d["id"]   for d in batch],
            documents = [d["text"] for d in batch],
            metadatas = [d["meta"] for d in batch],
        )
        print(f"  [{collection.name}] {min(i + batch_size, total)}/{total}", end="\r")
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
    client, ef = get_client_and_ef()
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
    print(f"  knowledge : {col_knowledge.count()} docs")
    print(f"  facts     : {col_facts.count()} docs")
    print(f"  style     : {col_style.count()} docs")

if __name__ == "__main__":
    main()
"""
ingest_chatgpt.py
Parses your ChatGPT export and loads it into ChromaDB.

Usage (from backend folder with venv active):
    python ingest_chatgpt.py --input "C:\path\to\conversations-000.json"

To ingest all files at once:
    python ingest_chatgpt.py --input "C:\path\to\conversations-*.json"

To wipe existing ChatGPT entries first:
    python ingest_chatgpt.py --input "C:\path\to\conversations-000.json" --wipe

To process multiple files:
    python ingest_chatgpt.py --input "C:\path\conversations-000.json" "C:\path\conversations-001.json" --wipe
"""

import json
import argparse
import glob
import re
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

# ── Config ───────────────────────────────────────────────────────────────────
CHROMA_PATH   = "./chroma_db"
EMBED_MODEL   = "all-MiniLM-L6-v2"
CHUNK_SIZE    = 800
CHUNK_OVERLAP = 100

# ── ChromaDB setup ────────────────────────────────────────────────────────────
def get_client_and_ef():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    return client, ef

# ── Helpers ───────────────────────────────────────────────────────────────────
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
    if isinstance(ts, (int, float)) and ts > 0:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return ""

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

def extract_messages(mapping: dict) -> list:
    """Walk the mapping tree and extract messages in order."""
    # Find root node (no parent)
    root = None
    for node_id, node in mapping.items():
        if node.get('parent') is None:
            root = node_id
            break

    if not root:
        return []

    # Walk tree following children
    messages = []
    visited = set()
    queue = [root]

    while queue:
        node_id = queue.pop(0)
        if node_id in visited:
            continue
        visited.add(node_id)

        node = mapping.get(node_id, {})
        msg = node.get('message')

        if msg:
            role = msg.get('author', {}).get('role', '')
            content = msg.get('content', {})
            parts = content.get('parts', [])
            text = ' '.join([p for p in parts if isinstance(p, str)]).strip()
            ts = parse_timestamp(msg.get('create_time'))

            if text and role in ('user', 'assistant'):
                messages.append({
                    'role': role,
                    'text': text,
                    'timestamp': ts,
                })

        # Add children to queue
        children = node.get('children', [])
        queue.extend(children)

    return messages

# ── Parse conversations ────────────────────────────────────────────────────────
def parse_file(path: str):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not isinstance(data, list):
        print(f"  Unexpected format in {path}")
        return [], [], []

    knowledge_docs = []
    facts_docs     = []
    style_docs     = []

    skipped = 0

    for conv in data:
        conv_id  = conv.get('id') or conv.get('conversation_id', 'unknown')
        title    = conv.get('title', 'Untitled')
        created  = parse_timestamp(conv.get('create_time'))
        mapping  = conv.get('mapping', {})

        if not mapping:
            skipped += 1
            continue

        messages = extract_messages(mapping)
        if not messages:
            skipped += 1
            continue

        # Only store user messages in facts/style/knowledge
        user_messages = [m for m in messages if m['role'] == 'user']

        if not user_messages:
            skipped += 1
            continue

        # ── knowledge: only YOUR messages chunked together ──
        user_text = f"Conversation: {title}\n\n" + "\n\n".join(
            f"[You]: {m['text']}" for m in user_messages
        )
        for i, chunk in enumerate(chunk_text(user_text)):
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
                    "category":   classify_memory(chunk),
                }
            })

        # ── facts: each user message ──
        for j, m in enumerate(user_messages):
            if len(m['text'].strip()) > 20:
                facts_docs.append({
                    "id":   f"cgpt_fact_{conv_id}_{j}",
                    "text": m['text'].strip(),
                    "meta": {
                        "source":     "chatgpt",
                        "conv_id":    conv_id,
                        "title":      title,
                        "created_at": m['timestamp'] or created,
                        "type":       "fact",
                        "category":   classify_memory(m['text']),
                    }
                })

        # ── style: longer user messages ──
        for k, m in enumerate([m for m in user_messages if len(m['text']) > 80]):
            style_docs.append({
                "id":   f"cgpt_style_{conv_id}_{k}",
                "text": m['text'].strip(),
                "meta": {
                    "source":     "chatgpt",
                    "conv_id":    conv_id,
                    "title":      title,
                    "created_at": m['timestamp'] or created,
                    "type":       "style",
                    "category":   classify_memory(m['text']),
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
        print(f"  [{collection.name}] {min(i + batch_size, total)}/{total}", end="\r")
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
    client, ef = get_client_and_ef()
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
    print(f"  knowledge : {col_knowledge.count()} docs")
    print(f"  facts     : {col_facts.count()} docs")
    print(f"  style     : {col_style.count()} docs")

if __name__ == "__main__":
    main()

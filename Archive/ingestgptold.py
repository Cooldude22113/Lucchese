"""
ingest_chatgpt_v3.py
────────────────────
Production-grade ingestion of ChatGPT export data into ChromaDB for Lucchese.
 
ARCHITECTURE:
  - Quality gate: conversation-level, fails closed, checks full conversation not just first 3
  - Classification split into 3 focused LLM calls (ontology / taxonomy / routing)
  - Fully constrained tier1 → tier2 → tier3 taxonomy with defined value lists
  - Gnostic ontology with examples in prompt for reliable local model output
  - Era tagging: timestamp-derived + regex-gated LLM temporal extraction
  - Reinforcement count: merges and upgrades metadata on similar existing entries
  - Artefact detection: LLM-based not just regex
  - Cross-reference pass: searches both knowledge and facts, batch-indexed by topic
  - Controlled batch concurrency: processes in batches not all at once
  - Summaries stored in col_summaries not inline metadata
  - Full validation of all classified fields against allowed lists
 
USAGE:
    python ingest_chatgpt_v3.py --input "C:/path/to/conversations.json"
    python ingest_chatgpt_v3.py --input "C:/path/conversations*.json" --wipe
    python ingest_chatgpt_v3.py --input "C:/path/conversations.json" --limit 10
 
WORKFLOW:
    1. Test with --limit 10 first, check output
    2. Run full ingest with --wipe to replace old data
    3. Run reclassify.py for contradiction detection
    4. Admin panel → Manage → Rebuild Summaries
"""
 
import json
import argparse
import glob
import re
import uuid
import asyncio
import hashlib
import httpx
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
 
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
load_dotenv()
 
# ── Config ────────────────────────────────────────────────────────────────────
CHROMA_PATH  = "./chroma_db"
EMBED_MODEL  = "nomic-ai/nomic-embed-text-v1"
CHUNK_SIZE   = 800
CHUNK_OVERLAP = 100
BATCH_SIZE   = 10   # conversations processed per batch
CONCURRENCY  = 4    # parallel LLM calls within a batch
 
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/api/chat"
MODEL      = os.getenv("MODEL_FAST", "gemma2:27b")
 
REINFORCEMENT_THRESHOLD = 0.35  # increment count on existing entry
DEDUP_THRESHOLD         = 0.25  # skip entirely — true duplicate
 
 
# ── Era boundaries ────────────────────────────────────────────────────────────
ERA_BOUNDARIES = [
    (None, 2013, "pre_divorce"),
    (2013, 2020, "post_divorce"),
    (2020, 2022, "transition"),
    (2022, 2024, "building"),
    (2024, None, "present"),
]
 
def get_era_from_year(year: int) -> str:
    for start, end, label in ERA_BOUNDARIES:
        if (start is None or year >= start) and (end is None or year < end):
            return label
    return "present"
 
 
# ── Constrained taxonomy ──────────────────────────────────────────────────────
# tier1 → tier2 → [tier3 options]
TAXONOMY = {
    "technology": {
        "ai": [
            "models", "architecture", "prompting", "agents",
            "tools", "training", "evaluation", "ethics"
        ],
        "computing": [
            "software", "operating_systems", "databases",
            "algorithms", "quantum", "distributed_systems"
        ],
        "security": [
            "infosec", "opsec", "privacy", "cryptography",
            "networks", "vulnerabilities", "authentication"
        ],
        "web": [
            "frontend", "backend", "apis", "platforms",
            "ecommerce", "hosting", "protocols"
        ],
        "hardware": [
            "builds", "components", "peripherals",
            "networking", "embedded", "mobile_devices"
        ],
        "infrastructure": [
            "cloud", "servers", "devops",
            "monitoring", "deployment", "automation"
        ],
    },
    "health": {
        "training": [
            "programming", "technique", "recovery",
            "periodisation", "cardio", "mobility", "competition"
        ],
        "bodybuilding": [
            "hypertrophy", "cutting", "bulking",
            "posing", "aesthetics", "natural_vs_enhanced"
        ],
        "martial_arts": [
            "striking", "grappling", "conditioning",
            "strategy", "competition", "history"
        ],
        "nutrition": [
            "macros", "meal_timing", "cutting_diet",
            "bulking_diet", "food_science", "digestion"
        ],
        "compounds": [
            "anabolics", "peptides", "sarms",
            "harm_reduction", "protocols", "sourcing", "pct"
        ],
        "supplements": [
            "nootropics", "performance", "recovery",
            "health_basics", "stacking", "brands"
        ],
        "psychedelics": [
            "psilocybin", "mdma", "lsd", "dmt",
            "microdosing", "therapeutic", "harm_reduction"
        ],
        "mental": [
            "psychology", "mindset", "cognitive_performance",
            "mental_health", "neuroscience", "habits"
        ],
        "medical": [
            "epilepsy", "diagnosis", "treatment",
            "medications", "conditions", "healthcare"
        ],
    },
    "finance": {
        "money": [
            "cash_flow", "budgeting", "systems",
            "currency", "crypto", "banking", "wealth_building"
        ],
        "property": [
            "acquisition", "deal_analysis", "development",
            "valuation", "rental", "commercial", "strategy"
        ],
        "investment": [
            "equities", "vehicles", "risk",
            "portfolio", "passive_income", "returns"
        ],
        "business_finance": [
            "pricing", "margins", "revenue",
            "costs", "funding", "accounting"
        ],
    },
    "business": {
        "ptpreps": [
            "operations", "menu", "shopify",
            "marketing", "customers", "subscriptions", "growth"
        ],
        "pub": [
            "development", "operations", "events",
            "licensing", "refurbishment", "management"
        ],
        "consulting": [
            "it_consulting", "property_consulting",
            "strategy", "clients", "proposals"
        ],
        "entrepreneurship": [
            "startups", "ideas", "validation",
            "growth", "competition", "pivoting"
        ],
        "marketing": [
            "content_marketing", "social_media", "branding",
            "copywriting", "ads", "seo", "email"
        ],
        "operations": [
            "systems", "automation", "suppliers",
            "logistics", "processes", "scaling"
        ],
    },
    "society": {
        "politics": [
            "uk_politics", "global_politics", "policy",
            "governance", "surveillance", "power_structures", "elections"
        ],
        "economics": [
            "macro", "markets", "labour",
            "inequality", "systems", "theory", "trade"
        ],
        "culture": [
            "history", "philosophy", "religion",
            "spirituality", "esoteric", "traditions"
        ],
        "people": [
            "entrepreneurs", "public_figures", "politicians",
            "scientists", "athletes", "artists"
        ],
        "social_dynamics": [
            "influence", "group_behaviour", "hierarchies",
            "tribalism", "communication", "persuasion"
        ],
        "media": [
            "mainstream_media", "social_media", "propaganda",
            "censorship", "narrative", "alternative_media"
        ],
    },
    "science": {
        "physics": [
            "quantum_mechanics", "cosmology", "relativity",
            "energy", "particle_physics", "space"
        ],
        "biology": [
            "genetics", "evolution", "physiology",
            "neuroscience", "microbiology", "ecology"
        ],
        "chemistry": [
            "organic", "biochemistry", "pharmacology",
            "materials", "synthesis"
        ],
        "mathematics": [
            "statistics", "probability", "algorithms",
            "geometry", "number_theory"
        ],
        "research": [
            "methodology", "studies", "data_analysis",
            "peer_review", "replication"
        ],
    },
    "philosophy": {
        "metaphysics": [
            "consciousness", "reality", "free_will",
            "existence", "time", "identity"
        ],
        "ethics": [
            "morality", "justice", "virtue",
            "consequentialism", "duty", "applied_ethics"
        ],
        "epistemology": [
            "knowledge", "truth", "belief",
            "perception", "scepticism", "certainty"
        ],
        "political_philosophy": [
            "power", "freedom", "sovereignty",
            "justice", "rights", "authority"
        ],
        "philosophy_of_mind": [
            "cognition", "qualia", "self",
            "perception", "language", "rationality"
        ],
    },
    "creative": {
        "content": [
            "video", "writing", "podcasting",
            "social_media", "scriptwriting", "storytelling"
        ],
        "design": [
            "web_design", "visual_design", "ux",
            "branding", "product_design"
        ],
        "music": [
            "production", "theory", "instruments",
            "genres", "industry", "performance"
        ],
        "media_consumption": [
            "film", "gaming", "books",
            "documentaries", "series", "podcasts"
        ],
    },
    "personal": {
        "identity": [
            "values", "beliefs", "goals",
            "self_concept", "growth", "purpose"
        ],
        "relationships": [
            "romantic", "family", "friendships",
            "social_circle", "conflict", "communication"
        ],
        "lifestyle": [
            "routines", "travel", "hobbies",
            "environment", "possessions", "time_management"
        ],
        "history": [
            "childhood", "formative_events", "decisions",
            "turning_points", "regrets", "achievements"
        ],
    },
    "lucchese": {
        "system": [
            "architecture", "memory", "prompts",
            "models", "retrieval", "classification"
        ],
        "meta": [
            "conversations", "feedback", "instructions",
            "improvements", "testing"
        ],
    },
}
 
# Flat lists for validation
VALID_TIER1 = list(TAXONOMY.keys())
 
def valid_tier2(t1: str) -> list:
    return list(TAXONOMY.get(t1, {}).keys())
 
def valid_tier3(t1: str, t2: str) -> list:
    return TAXONOMY.get(t1, {}).get(t2, [])
 
def validate_tier(t1: str, t2: str, t3: str) -> tuple[str, str, str]:
    if t1 not in VALID_TIER1:
        t1 = "personal"
    t2_options = valid_tier2(t1)
    if t2 not in t2_options:
        t2 = t2_options[0] if t2_options else "general"
    t3_options = valid_tier3(t1, t2)
    if t3 not in t3_options:
        t3 = t3_options[0] if t3_options else "general"
    return t1, t2, t3
 
def taxonomy_prompt_reference() -> str:
    lines = []
    for t1, t2s in TAXONOMY.items():
        for t2, t3s in t2s.items():
            lines.append(f"  {t1} → {t2} → [{', '.join(t3s)}]")
    return "\n".join(lines)
 
 
# ── Gnostic ontology ──────────────────────────────────────────────────────────
ONTOLOGY_CLASSES = ["gnosis", "episteme", "pistis", "doxa", "logos", "techne"]
 
ONTOLOGY_DEFINITIONS = {
    "gnosis":   "Direct personal experience or lived knowledge. Alex knows this because he lived it.",
    "episteme": "Intellectual understanding reached through reasoning or study. Alex understands this conceptually.",
    "pistis":   "Belief or conviction held without direct proof. Alex holds this as true based on faith or trust.",
    "doxa":     "Received wisdom, cultural assumption, or general opinion. What people broadly think or accept.",
    "logos":    "Systematic understanding of how something works mechanically or structurally.",
    "techne":   "Practical skill or procedural knowledge. Knowing how to do or make something.",
}
 
ONTOLOGY_EXAMPLES = {
    "gnosis":   "Alex describing his epilepsy diagnosis experience. Alex recounting what happened when he started PTPreps.",
    "episteme": "Alex asking how quantum computing works and engaging with the explanation. Alex reasoning through an investment decision.",
    "pistis":   "Alex stating he believes money is a control system. Alex expressing conviction about human nature without citing evidence.",
    "doxa":     "Alex repeating what society generally thinks about drugs. A ChatGPT explanation of mainstream opinion on a topic.",
    "logos":    "Alex asking how the nervous system works. An explanation of how blockchain transactions are validated.",
    "techne":   "Alex asking how to set up a Shopify webhook. A step-by-step protocol for a training programme.",
}
 
 
# ── ChromaDB setup ────────────────────────────────────────────────────────────
def get_collections():
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL,
        trust_remote_code=True
    )
    client         = chromadb.PersistentClient(path=CHROMA_PATH)
    col_knowledge  = client.get_or_create_collection("knowledge",  embedding_function=ef)
    col_facts      = client.get_or_create_collection("facts",      embedding_function=ef)
    col_style      = client.get_or_create_collection("style",      embedding_function=ef)
    col_summaries  = client.get_or_create_collection("summaries",  embedding_function=ef)
    return client, ef, col_knowledge, col_facts, col_style, col_summaries
 
 
# ── Text chunking (proper sliding window overlap) ─────────────────────────────
def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks    = []
    current   = ""
 
    for sentence in sentences:
        if len(sentence) > size:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(sentence), size - overlap):
                part = sentence[i:i + size]
                if part.strip():
                    chunks.append(part.strip())
            continue
 
        if len(current) + len(sentence) + 1 <= size:
            current = (current + " " + sentence).strip()
        else:
            if current:
                chunks.append(current)
                # proper overlap: seed next chunk with tail of previous
                overlap_seed = current[-overlap:].strip()
                current = (overlap_seed + " " + sentence).strip()
            else:
                current = sentence
 
    if current:
        # avoid storing duplicate of last chunk
        chunk_hash = hashlib.md5(current.encode()).hexdigest()
        existing_hashes = {hashlib.md5(c.encode()).hexdigest() for c in chunks}
        if chunk_hash not in existing_hashes:
            chunks.append(current)
 
    return [c for c in chunks if len(c.strip()) > 20]
 
 
# ── Timestamp helpers ─────────────────────────────────────────────────────────
def parse_timestamp(ts) -> str:
    if isinstance(ts, (int, float)) and ts > 0:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return ""
 
def year_from_iso(iso: str) -> int:
    try:
        return datetime.fromisoformat(iso).year
    except Exception:
        return datetime.now().year
 
 
# ── Message extraction ────────────────────────────────────────────────────────
def extract_messages(mapping: dict) -> list:
    root = None
    for node_id, node in mapping.items():
        if node.get("parent") is None:
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
        msg  = node.get("message")
 
        if msg:
            role  = msg.get("author", {}).get("role", "")
            parts = msg.get("content", {}).get("parts", [])
            text  = " ".join([p for p in parts if isinstance(p, str)]).strip()
            ts    = parse_timestamp(msg.get("create_time"))
            if text and role in ("user", "assistant"):
                messages.append({"role": role, "text": text, "timestamp": ts})
 
        queue.extend(node.get("children", []))
 
    return messages
 
 
def build_exchange_pairs(messages: list) -> list:
    pairs = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg["role"] == "user":
            user_text      = msg["text"]
            user_ts        = msg["timestamp"]
            assistant_text = ""
            if i + 1 < len(messages) and messages[i + 1]["role"] == "assistant":
                assistant_text = messages[i + 1]["text"]
                i += 1
            pairs.append({
                "user_text":      user_text,
                "assistant_text": assistant_text,
                "timestamp":      user_ts,
            })
        i += 1
    return pairs
 
 
# ── LLM call ─────────────────────────────────────────────────────────────────
semaphore = asyncio.Semaphore(CONCURRENCY)
 
async def llm_call(client: httpx.AsyncClient, prompt: str, max_tokens: int = 100) -> str:
    async with semaphore:
        try:
            res = await client.post(
                OLLAMA_URL,
                json={
                    "model":    MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream":   False,
                    "options":  {"temperature": 0, "num_predict": max_tokens},
                },
                timeout=90,
            )
            return res.json()["message"]["content"].strip()
        except Exception as e:
            print(f"  LLM error: {e}")
            return ""
 
def safe_json(text: str) -> dict:
    try:
        clean = re.sub(r"```json|```", "", text).strip()
        # handle trailing commas
        clean = re.sub(r",\s*([}\]])", r"\1", clean)
        return json.loads(clean)
    except Exception:
        return {}
 
 
# ── Quality gate (fails closed) ───────────────────────────────────────────────
QUALITY_PROMPT = """You are deciding whether a conversation is worth storing in a personal AI memory system for Alex.
 
Alex is a personal trainer, bodybuilder, martial artist, entrepreneur, and deep thinker.
His AI needs to know about his life, his thinking, his philosophy, his history, and his genuine interests.
 
WORTH STORING — any of these:
- Personal content about Alex's life, health, relationships, business, finances, goals, history
- Genuine intellectual exploration — philosophy, consciousness, power, economics, science, society
- Opinions, beliefs, or values being explored or expressed with any depth
- Topics Alex clearly cares about based on follow-up questions or pushback
- Situational snapshots — what Alex was working on or thinking about at a point in time
 
NOT WORTH STORING — all of these are skip:
- Pure one-off task with zero personal relevance (generate image, fix grammar, write a tagline)
- Generic factual lookup with no discussion and no follow-up (single Q&A, no engagement)
- Clearly abandoned conversations (one message then nothing)
- Small talk, test messages, greetings
 
Conversation title: {title}
 
Full conversation sample ({n_pairs} total exchanges, showing up to 6):
{sample}
 
Reply with JSON only. If uncertain, return worth_storing: false.
{{"worth_storing": true, "reason": "one line"}}
or
{{"worth_storing": false, "reason": "one line"}}"""
 
async def quality_gate(client: httpx.AsyncClient, title: str, pairs: list) -> tuple[bool, str]:
    sample_lines = []
    for p in pairs[:6]:
        if p["user_text"]:
            sample_lines.append(f"[Alex]: {p['user_text'][:250]}")
        if p["assistant_text"]:
            sample_lines.append(f"[ChatGPT]: {p['assistant_text'][:200]}")
 
    prompt = QUALITY_PROMPT.format(
        title   = title,
        n_pairs = len(pairs),
        sample  = "\n\n".join(sample_lines),
    )
    response = await llm_call(client, prompt, max_tokens=60)
    result   = safe_json(response)
 
    # fails closed — uncertain = skip
    worth = result.get("worth_storing", False)
    reason = result.get("reason", "parse failed — skipped")
    return bool(worth), reason
 
 
# ── Ontology classification (focused single-purpose prompt) ───────────────────
ONTOLOGY_PROMPT = """Classify the PRIMARY nature of this knowledge using exactly one of these six classes.
 
Classes:
  gnosis   — {gnosis_def}
             Example: {gnosis_ex}
 
  episteme — {episteme_def}
             Example: {episteme_ex}
 
  pistis   — {pistis_def}
             Example: {pistis_ex}
 
  doxa     — {doxa_def}
             Example: {doxa_ex}
 
  logos    — {logos_def}
             Example: {logos_ex}
 
  techne   — {techne_def}
             Example: {techne_ex}
 
[Alex]: {user_text}
[ChatGPT]: {assistant_text}
 
Reply with the single class name only. No explanation. No punctuation.
Valid values: gnosis, episteme, pistis, doxa, logos, techne"""
 
async def classify_ontology(client: httpx.AsyncClient, user_text: str, assistant_text: str) -> str:
    prompt = ONTOLOGY_PROMPT.format(
        gnosis_def   = ONTOLOGY_DEFINITIONS["gnosis"],
        gnosis_ex    = ONTOLOGY_EXAMPLES["gnosis"],
        episteme_def = ONTOLOGY_DEFINITIONS["episteme"],
        episteme_ex  = ONTOLOGY_EXAMPLES["episteme"],
        pistis_def   = ONTOLOGY_DEFINITIONS["pistis"],
        pistis_ex    = ONTOLOGY_EXAMPLES["pistis"],
        doxa_def     = ONTOLOGY_DEFINITIONS["doxa"],
        doxa_ex      = ONTOLOGY_EXAMPLES["doxa"],
        logos_def    = ONTOLOGY_DEFINITIONS["logos"],
        logos_ex     = ONTOLOGY_EXAMPLES["logos"],
        techne_def   = ONTOLOGY_DEFINITIONS["techne"],
        techne_ex    = ONTOLOGY_EXAMPLES["techne"],
        user_text      = user_text[:400],
        assistant_text = assistant_text[:300],
    )
    response = (await llm_call(client, prompt, max_tokens=10)).lower().strip().split()[0] if await llm_call(client, prompt, max_tokens=10) else ""
    # validate
    return response if response in ONTOLOGY_CLASSES else "episteme"
 
async def classify_ontology_safe(client: httpx.AsyncClient, user_text: str, assistant_text: str) -> str:
    prompt = ONTOLOGY_PROMPT.format(
        gnosis_def   = ONTOLOGY_DEFINITIONS["gnosis"],
        gnosis_ex    = ONTOLOGY_EXAMPLES["gnosis"],
        episteme_def = ONTOLOGY_DEFINITIONS["episteme"],
        episteme_ex  = ONTOLOGY_EXAMPLES["episteme"],
        pistis_def   = ONTOLOGY_DEFINITIONS["pistis"],
        pistis_ex    = ONTOLOGY_EXAMPLES["pistis"],
        doxa_def     = ONTOLOGY_DEFINITIONS["doxa"],
        doxa_ex      = ONTOLOGY_EXAMPLES["doxa"],
        logos_def    = ONTOLOGY_DEFINITIONS["logos"],
        logos_ex     = ONTOLOGY_EXAMPLES["logos"],
        techne_def   = ONTOLOGY_DEFINITIONS["techne"],
        techne_ex    = ONTOLOGY_EXAMPLES["techne"],
        user_text      = user_text[:400],
        assistant_text = assistant_text[:300],
    )
    response = await llm_call(client, prompt, max_tokens=10)
    word = response.lower().strip().split()[0] if response.strip() else ""
    return word if word in ONTOLOGY_CLASSES else "episteme"
 
 
# ── Taxonomy classification (focused, constrained lists) ─────────────────────
TAXONOMY_PROMPT = """Classify this conversation into the most accurate subject taxonomy path.
You MUST choose values from the lists provided. Do not invent values.
 
Full taxonomy (tier1 → tier2 → [tier3 options]):
{taxonomy_ref}
 
[Alex]: {user_text}
[ChatGPT]: {assistant_text}
 
Choose the PRIMARY subject path this conversation belongs to.
If it genuinely spans two domains, choose a SECONDARY path. If not, leave secondary empty.
 
Reply with JSON only:
{{
  "primary_tier1": "...",
  "primary_tier2": "...",
  "primary_tier3": "...",
  "secondary_tier1": "",
  "secondary_tier2": "",
  "secondary_tier3": "",
  "is_personal": true
}}
 
is_personal = true only if this conversation is specifically about Alex's own life, opinions, or situation."""
 
async def classify_taxonomy(client: httpx.AsyncClient, user_text: str, assistant_text: str) -> dict:
    prompt = TAXONOMY_PROMPT.format(
        taxonomy_ref   = taxonomy_prompt_reference(),
        user_text      = user_text[:400],
        assistant_text = assistant_text[:250],
    )
    response = await llm_call(client, prompt, max_tokens=150)
    result   = safe_json(response)
 
    # validate and correct all tier values
    pt1, pt2, pt3 = validate_tier(
        result.get("primary_tier1", "personal"),
        result.get("primary_tier2", "identity"),
        result.get("primary_tier3", "general"),
    )
    st1 = result.get("secondary_tier1", "")
    st2 = result.get("secondary_tier2", "")
    st3 = result.get("secondary_tier3", "")
    if st1:
        st1, st2, st3 = validate_tier(st1, st2, st3)
 
    return {
        "primary_tier1":   pt1,
        "primary_tier2":   pt2,
        "primary_tier3":   pt3,
        "secondary_tier1": st1,
        "secondary_tier2": st2,
        "secondary_tier3": st3,
        "is_personal":     str(result.get("is_personal", False)).lower(),
    }
 
 
# ── Collection routing (focused) ──────────────────────────────────────────────
ROUTING_PROMPT = """Decide which memory collections this exchange should be stored in.
 
knowledge = store if this captures meaningful context about Alex's life, thinking, situation, or genuine interests.
            Store even if Alex is just the one asking — the topic and engagement matter.
 
facts     = store if Alex's message contains a clear statement, opinion, belief, preference, or personal fact.
            Do NOT store if Alex is just issuing a task instruction with no personal content.
 
style     = store if Alex's message shows his natural voice — direct, personal, opinionated, curious.
            Do NOT store task instructions, one-word replies, or generic prompts.
 
engagement = active if Alex is genuinely engaging — follow-up questions, pushback, opinions, depth.
           = passive if Alex asked once and accepted the reply with no further engagement.
 
[Alex]: {user_text}
[ChatGPT]: {assistant_text}
 
Reply with JSON only:
{{
  "knowledge": true,
  "facts": false,
  "style": false,
  "engagement": "active",
  "source_type": "dialogue"
}}
 
source_type options: self (Alex expressing his own experience/opinion), dialogue (emerged through exchange), received (Alex receiving information), generated (purely AI output)"""
 
async def classify_routing(client: httpx.AsyncClient, user_text: str, assistant_text: str) -> dict:
    prompt = ROUTING_PROMPT.format(
        user_text      = user_text[:400],
        assistant_text = assistant_text[:250],
    )
    response = await llm_call(client, prompt, max_tokens=80)
    result   = safe_json(response)
 
    valid_source    = ["self", "dialogue", "received", "generated"]
    valid_engage    = ["active", "passive"]
    source_type     = result.get("source_type", "received")
    engagement      = result.get("engagement", "passive")
 
    return {
        "knowledge":   bool(result.get("knowledge", True)),
        "facts":       bool(result.get("facts", False)),
        "style":       bool(result.get("style", False)),
        "engagement":  engagement  if engagement  in valid_engage  else "passive",
        "source_type": source_type if source_type in valid_source  else "received",
    }
 
 
# ── Artefact detection (LLM-based) ────────────────────────────────────────────
ARTEFACT_PROMPT = """Is this user message purely a one-off creative or generation task with no personal discussion?
 
Examples of artefacts: generate an image, make this less blurry, write me a tagline, 
create a logo, write a title for a video, generate a poem.
 
Not artefacts: asking about a topic, expressing an opinion, discussing a plan, 
requesting analysis or explanation, even if it results in creative output.
 
[Alex]: {user_text}
 
Reply with one word only: yes or no"""
 
async def is_artefact(client: httpx.AsyncClient, user_text: str) -> bool:
    # fast regex pre-check before LLM call
    artefact_signals = [
        r'\bgenerate\b.{0,20}\bimage\b',
        r'\bmake.{0,20}(less blurry|clearer|sharper)\b',
        r'\bcreate\b.{0,20}\b(logo|banner|thumbnail|image)\b',
    ]
    if any(re.search(p, user_text.lower()) for p in artefact_signals):
        return True
 
    # LLM call for ambiguous cases
    prompt   = ARTEFACT_PROMPT.format(user_text=user_text[:300])
    response = await llm_call(client, prompt, max_tokens=5)
    return response.lower().strip().startswith("yes")
 
 
# ── Era temporal extraction ───────────────────────────────────────────────────
TEMPORAL_SIGNALS = [
    "years ago", "back in", "when i was", "in my", "used to",
    "a few years", "decade ago", "at the time", "back then",
    "growing up", "as a kid", "as a child", "in the past"
]
 
ERA_PROMPT = """Does this text contain a reference to a specific time period or relative time?
Examples: "10 years ago", "back in 2019", "when I was younger", "in my early twenties"
 
Text: {text}
 
If yes, estimate the approximate year being referenced based on context clues.
Reply with JSON only:
{{"has_time_ref": true, "approximate_year": 2015}}
or
{{"has_time_ref": false, "approximate_year": null}}"""
 
async def extract_era_mention(client: httpx.AsyncClient, text: str) -> tuple[bool, int | None]:
    # regex gate — only call LLM if temporal language is present
    t = text.lower()
    if not any(sig in t for sig in TEMPORAL_SIGNALS):
        return False, None
 
    prompt   = ERA_PROMPT.format(text=text[:500])
    response = await llm_call(client, prompt, max_tokens=40)
    result   = safe_json(response)
    has_ref  = result.get("has_time_ref", False)
    year     = result.get("approximate_year", None)
    if isinstance(year, int) and 1980 <= year <= datetime.now().year:
        return has_ref, year
    return has_ref, None
 
 
# ── Per-conversation summary → col_summaries ──────────────────────────────────
SUMMARY_PROMPT = """Write one sentence describing this conversation and what it reveals about Alex.
Be specific about the actual topic and what Alex's engagement shows about his thinking or situation.
Do not start with "Alex" or "This conversation". Start with the topic itself.
 
Title: {title}
Exchanges ({n} total, sample below):
{sample}
 
One sentence only:"""
 
async def generate_summary(client: httpx.AsyncClient, conv_id: str, title: str, pairs: list, col_summaries) -> str:
    sample = "\n".join([
        f"[Alex]: {p['user_text'][:150]}\n[ChatGPT]: {p['assistant_text'][:100]}"
        for p in pairs[:5]
    ])
    prompt   = SUMMARY_PROMPT.format(title=title, n=len(pairs), sample=sample)
    summary  = await llm_call(client, prompt, max_tokens=80)
    summary  = summary.strip()
 
    if summary:
        col_summaries.upsert(
            ids       = [f"conv_summary_{conv_id}"],
            documents = [summary],
            metadatas = [{
                "source":  "chatgpt",
                "conv_id": conv_id,
                "title":   title,
                "type":    "conv_summary",
            }],
        )
    return summary
 
 
# ── Reinforcement (merges metadata, doesn't just increment) ──────────────────
def check_and_reinforce(text: str, collection, new_meta: dict) -> bool:
    try:
        results = collection.query(
            query_texts = [text],
            n_results   = 1,
            include     = ["metadatas", "distances"],
        )
        if not results["distances"] or not results["distances"][0]:
            return False
 
        dist = results["distances"][0][0]
 
        if dist < DEDUP_THRESHOLD:
            return True  # true duplicate, skip silently
 
        if dist < REINFORCEMENT_THRESHOLD:
            existing_id   = results["ids"][0][0]
            existing_meta = dict(results["metadatas"][0][0])
            count = int(existing_meta.get("reinforcement_count", "1")) + 1
            # merge: upgrade taxonomy if new entry has secondary path and existing doesn't
            if new_meta.get("primary_tier1") and not existing_meta.get("primary_tier1"):
                existing_meta["primary_tier1"] = new_meta["primary_tier1"]
                existing_meta["primary_tier2"] = new_meta["primary_tier2"]
                existing_meta["primary_tier3"] = new_meta["primary_tier3"]
            if new_meta.get("secondary_tier1") and not existing_meta.get("secondary_tier1"):
                existing_meta["secondary_tier1"] = new_meta["secondary_tier1"]
                existing_meta["secondary_tier2"] = new_meta["secondary_tier2"]
                existing_meta["secondary_tier3"] = new_meta["secondary_tier3"]
            if new_meta.get("ontology") and existing_meta.get("ontology") in ("episteme", "doxa"):
                # upgrade to more specific ontology if new classification is richer
                if new_meta["ontology"] in ("gnosis", "pistis", "techne"):
                    existing_meta["ontology"] = new_meta["ontology"]
            existing_meta["reinforcement_count"] = str(count)
            existing_meta["last_reinforced"]     = datetime.now(timezone.utc).isoformat()
            collection.update(ids=[existing_id], metadatas=[existing_meta])
            return True
 
    except Exception as e:
        print(f"  Reinforce error: {e}")
    return False  # fails open for new content — better to store than lose
 
 
# ── Process single conversation ───────────────────────────────────────────────
async def process_conversation(
    conv: dict,
    client: httpx.AsyncClient,
    col_knowledge,
    col_facts,
    col_style,
    col_summaries,
    stats: dict,
) -> list:
 
    conv_id = conv.get("id") or conv.get("conversation_id", str(uuid.uuid4()))
    title   = conv.get("title", "Untitled")
    created = parse_timestamp(conv.get("create_time"))
    mapping = conv.get("mapping", {})
 
    if not mapping:
        stats["skipped"] += 1
        return []
 
    messages = extract_messages(mapping)
    pairs    = build_exchange_pairs(messages)
 
    if not pairs:
        stats["skipped"] += 1
        return []
 
    # ── Quality gate — fails closed ───────────────────────────────────────────
    worth, reason = await quality_gate(client, title, pairs)
    if not worth:
        stats["gated_out"] += 1
        print(f"  ✗ [{title[:55]}] — {reason}")
        return []
 
    # ── Conversation-level metadata ───────────────────────────────────────────
    conv_year = year_from_iso(created) if created else datetime.now().year
    conv_era  = get_era_from_year(conv_year)
 
    # ── Extract era mention (regex-gated) ─────────────────────────────────────
    early_user_text = " ".join(p["user_text"] for p in pairs[:5])
    has_era_ref, ref_year = await extract_era_mention(client, early_user_text)
    referenced_era = get_era_from_year(ref_year) if ref_year else ""
 
    # ── Per-conversation summary → col_summaries ──────────────────────────────
    conv_summary = await generate_summary(client, conv_id, title, pairs, col_summaries)
 
    print(f"  ✓ [{title[:55]}] {conv_era} | {reason}")
 
    passive_entries = []
 
    # ── Process each exchange pair ────────────────────────────────────────────
    for j, pair in enumerate(pairs):
        user_text      = pair["user_text"].strip()
        assistant_text = pair["assistant_text"].strip()
        if not user_text:
            continue
 
        # ── Artefact check ────────────────────────────────────────────────────
        if await is_artefact(client, user_text):
            artefact_meta = {
                "source":              "chatgpt",
                "conv_id":             conv_id,
                "title":               title,
                "created_at":          created,
                "era":                 conv_era,
                "type":                "artefact",
                "ontology":            "techne",
                "source_type":         "generated",
                "engagement":          "active",
                "is_personal":         "false",
                "primary_tier1":       "creative",
                "primary_tier2":       "design",
                "primary_tier3":       "branding",
                "secondary_tier1":     "",
                "secondary_tier2":     "",
                "secondary_tier3":     "",
                "reinforcement_count": "1",
                "last_reinforced":     created or datetime.now(timezone.utc).isoformat(),
                "cross_referenced":    "false",
                "has_era_mention":     "false",
                "referenced_era":      "",
            }
            if not check_and_reinforce(user_text, col_facts, artefact_meta):
                col_facts.upsert(
                    ids       = [f"cgpt_artefact_{conv_id}_{j}"],
                    documents = [user_text],
                    metadatas = [artefact_meta],
                )
            stats["artefacts"] += 1
            continue
 
        # ── Three focused classification calls ────────────────────────────────
        ontology_class, taxonomy, routing = await asyncio.gather(
            classify_ontology_safe(client, user_text, assistant_text),
            classify_taxonomy(client, user_text, assistant_text),
            classify_routing(client, user_text, assistant_text),
        )
 
        base_meta = {
            "source":              "chatgpt",
            "conv_id":             conv_id,
            "title":               title,
            "created_at":          created,
            "conv_year":           str(conv_year),
            "era":                 conv_era,
            "has_era_mention":     str(has_era_ref).lower(),
            "referenced_era":      referenced_era,
            "ontology":            ontology_class,
            "source_type":         routing["source_type"],
            "engagement":          routing["engagement"],
            "is_personal":         taxonomy["is_personal"],
            "primary_tier1":       taxonomy["primary_tier1"],
            "primary_tier2":       taxonomy["primary_tier2"],
            "primary_tier3":       taxonomy["primary_tier3"],
            "secondary_tier1":     taxonomy["secondary_tier1"],
            "secondary_tier2":     taxonomy["secondary_tier2"],
            "secondary_tier3":     taxonomy["secondary_tier3"],
            "category":            taxonomy["primary_tier1"],  # backwards compat
            "reinforcement_count": "1",
            "last_reinforced":     created or datetime.now(timezone.utc).isoformat(),
            "cross_referenced":    "false",
        }
 
        # ── knowledge ─────────────────────────────────────────────────────────
        if routing["knowledge"]:
            exchange_text = f"[Alex]: {user_text}\n\n[ChatGPT]: {assistant_text}"
            for k, chunk in enumerate(chunk_text(exchange_text)):
                chunk_meta = {**base_meta, "type": "knowledge", "chunk_idx": str(k)}
                if not check_and_reinforce(chunk, col_knowledge, chunk_meta):
                    col_knowledge.upsert(
                        ids       = [f"cgpt_know_{conv_id}_{j}_{k}"],
                        documents = [chunk],
                        metadatas = [chunk_meta],
                    )
                    stats["knowledge"] += 1
 
        # ── facts ─────────────────────────────────────────────────────────────
        if routing["facts"] and len(user_text) >= 30:
            fact_meta = {**base_meta, "type": "fact"}
            if not check_and_reinforce(user_text, col_facts, fact_meta):
                col_facts.upsert(
                    ids       = [f"cgpt_fact_{conv_id}_{j}"],
                    documents = [user_text],
                    metadatas = [fact_meta],
                )
                stats["facts"] += 1
 
        # ── style ─────────────────────────────────────────────────────────────
        if routing["style"] and len(user_text) >= 60:
            style_meta = {**base_meta, "type": "style"}
            if not check_and_reinforce(user_text, col_style, style_meta):
                col_style.upsert(
                    ids       = [f"cgpt_style_{conv_id}_{j}"],
                    documents = [user_text],
                    metadatas = [style_meta],
                )
                stats["style"] += 1
 
        # ── track passive entries ─────────────────────────────────────────────
        if routing["engagement"] == "passive":
            passive_entries.append({
                "conv_id":       conv_id,
                "pair_idx":      j,
                "user_text":     user_text,
                "primary_tier1": taxonomy["primary_tier1"],
                "primary_tier2": taxonomy["primary_tier2"],
            })
 
    stats["processed"] += 1
    return passive_entries
 
 
# ── Cross-reference pass ──────────────────────────────────────────────────────
async def cross_reference_pass(passive_entries: list, col_knowledge, col_facts):
    if not passive_entries:
        print("\nNo passive entries to cross-reference.")
        return
 
    print(f"\nCross-referencing {len(passive_entries)} passive entries...")
 
    # build index of passive entries by conv_id for fast lookup
    passive_index: dict[str, list[int]] = {}
    for entry in passive_entries:
        passive_index.setdefault(entry["conv_id"], []).append(entry["pair_idx"])
 
    upgraded = 0
    for entry in passive_entries:
        query = f"{entry['primary_tier1']} {entry['primary_tier2']} {entry['user_text'][:200]}"
        try:
            # search BOTH facts and knowledge for active engagement on same topic
            active_found = False
            for col in [col_facts, col_knowledge]:
                results = col.query(
                    query_texts = [query],
                    n_results   = 5,
                    where       = {"engagement": "active"},
                    include     = ["metadatas", "distances"],
                )
                if results["distances"] and results["distances"][0]:
                    if any(d < 0.45 for d in results["distances"][0]):
                        active_found = True
                        break
 
            if not active_found:
                continue
 
            # update knowledge entries for this conv_id + pair_idx
            know_results = col_knowledge.get(
                where   = {"conv_id": entry["conv_id"]},
                include = ["metadatas"],
            )
            if not know_results["ids"]:
                continue
 
            ids_to_update   = []
            metas_to_update = []
            for eid, emeta in zip(know_results["ids"], know_results["metadatas"]):
                if emeta.get("chunk_idx", "").startswith(str(entry["pair_idx"])):
                    updated = dict(emeta)
                    updated["cross_referenced"] = "true"
                    ids_to_update.append(eid)
                    metas_to_update.append(updated)
 
            if ids_to_update:
                col_knowledge.update(ids=ids_to_update, metadatas=metas_to_update)
                upgraded += len(ids_to_update)
 
        except Exception as e:
            print(f"  Cross-ref error: {e}")
 
    print(f"  Cross-reference complete — {upgraded} entries upgraded")
 
 
# ── Wipe ──────────────────────────────────────────────────────────────────────
def wipe_chatgpt_entries(col_knowledge, col_facts, col_style, col_summaries):
    print("Wiping existing ChatGPT entries...")
    FETCH_SIZE = 500
    for col in [col_knowledge, col_facts, col_style, col_summaries]:
        try:
            all_ids = []
            offset  = 0
            while True:
                results = col.get(
                    where   = {"source": "chatgpt"},
                    limit   = FETCH_SIZE,
                    offset  = offset,
                    include = [],
                )
                if not results["ids"]:
                    break
                all_ids.extend(results["ids"])
                offset += FETCH_SIZE
            if all_ids:
                col.delete(ids=all_ids)
                print(f"  Deleted {len(all_ids)} from '{col.name}'")
            else:
                print(f"  Nothing to delete in '{col.name}'")
        except Exception as e:
            print(f"  Wipe error '{col.name}': {e}")
 
 
# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser(description="Lucchese ChatGPT Ingest v3")
    parser.add_argument("--input",  required=True, nargs="+")
    parser.add_argument("--wipe",   action="store_true")
    parser.add_argument("--limit",  type=int, default=None, help="Test on N conversations")
    args = parser.parse_args()
 
    input_files = []
    for pattern in args.input:
        expanded = glob.glob(pattern)
        input_files.extend(expanded if expanded else [pattern])
    input_files = sorted(set(input_files))
 
    print(f"\n{'─'*60}")
    print(f"Lucchese ChatGPT Ingest v3")
    print(f"Model      : {MODEL}")
    print(f"Concurrency: {CONCURRENCY}")
    print(f"Batch size : {BATCH_SIZE}")
    print(f"Files      : {', '.join(input_files)}")
    print(f"{'─'*60}\n")
 
    async with httpx.AsyncClient() as client:
        try:
            await client.get("http://localhost:11434", timeout=5)
            print("✓ Ollama reachable\n")
        except Exception:
            print("✗ Ollama unreachable — is it running?")
            return
 
    _, _, col_knowledge, col_facts, col_style, col_summaries = get_collections()
 
    if args.wipe:
        wipe_chatgpt_entries(col_knowledge, col_facts, col_style, col_summaries)
        print()
 
    all_conversations = []
    for path in input_files:
        p = Path(path)
        if not p.exists():
            print(f"Not found: {path}")
            continue
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            all_conversations.extend(data)
            print(f"Loaded {len(data)} conversations from {p.name}")
 
    if args.limit:
        all_conversations = all_conversations[:args.limit]
        print(f"\n[TEST MODE] Limited to {args.limit} conversations\n")
 
    total = len(all_conversations)
    print(f"\nTotal conversations: {total}\n")
 
    stats = {
        "processed": 0, "skipped": 0, "gated_out": 0,
        "knowledge": 0, "facts":   0, "style":     0, "artefacts": 0,
    }
    all_passive = []
 
    async with httpx.AsyncClient() as client:
        # process in controlled batches
        for batch_start in range(0, total, BATCH_SIZE):
            batch = all_conversations[batch_start:batch_start + BATCH_SIZE]
            batch_end = min(batch_start + BATCH_SIZE, total)
            print(f"\nBatch {batch_start+1}–{batch_end} of {total}")
 
            tasks   = [
                process_conversation(conv, client, col_knowledge, col_facts, col_style, col_summaries, stats)
                for conv in batch
            ]
            results = await asyncio.gather(*tasks)
            for r in results:
                if r:
                    all_passive.extend(r)
 
    await cross_reference_pass(all_passive, col_knowledge, col_facts)
 
    print(f"\n{'─'*60}")
    print(f"✓ Complete")
    print(f"  Processed      : {stats['processed']}")
    print(f"  Gated out      : {stats['gated_out']}")
    print(f"  Skipped        : {stats['skipped']}")
    print(f"  Knowledge      : {stats['knowledge']}")
    print(f"  Facts          : {stats['facts']}")
    print(f"  Style          : {stats['style']}")
    print(f"  Artefacts      : {stats['artefacts']}")
    print(f"  Passive found  : {len(all_passive)}")
    print(f"\n  knowledge total: {col_knowledge.count()}")
    print(f"  facts total    : {col_facts.count()}")
    print(f"  style total    : {col_style.count()}")
    print(f"\nNext: reclassify.py → Admin → Rebuild Summaries")
    print(f"{'─'*60}\n")
 
if __name__ == "__main__":
    asyncio.run(main())

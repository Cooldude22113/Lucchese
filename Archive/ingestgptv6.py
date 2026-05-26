"""
ingest_chatgpt_v4.py
────────────────────
Production-grade ingestion of ChatGPT export data into ChromaDB for Lucchese.

CHANGES FROM v3:
  - Full file logging: gate decisions, ontology calls, validate_tier corrections,
    reinforcement events — full audit trail
  - Dead classify_ontology function deleted (was making TWO LLM calls per invocation)
  - Ontology failure now stores "unknown" not "episteme" — unknown is honest
  - validate_tier logs every correction with original and replacement values
  - validate_tier uses explicit per-tier1 safe defaults, not index-zero fallback
  - source_type moved OUT of routing prompt, INTO ontology prompt (same concern)
  - Taxonomy classification split into two calls: tier1 first (short), tier2/3 second
    (narrowed options for that tier1 only — massively reduced context window usage)
  - Quality gate samples start + middle + end, not just first 6 exchanges
  - Era extraction scans ALL user messages, not just first 5
  - pair_idx stored in knowledge chunk metadata for exact cross-reference lookup
  - chunk_idx startswith bug fixed — exact pair_idx string equality comparison
  - Ontology validated in check_and_reinforce before writing to existing entry
  - TEMPORAL_SIGNALS tightened — removed "in my" and "at the time" (too many false positives)

V5 IMPROVEMENTS:
  - check_and_reinforce wrapped with asyncio.to_thread at all call sites
    (sync ChromaDB calls were blocking the entire event loop on every exchange)
  - ONTOLOGY_PRIORITY dict replaces ad-hoc upgrade checks — explicit hierarchy,
    no gaps (e.g. logos → gnosis upgrade now works correctly)
  - Per-exchange minimum content floor: skip pairs < 5 user words + < 20 assistant words
  - classify_taxonomy split into classify_taxonomy_tier1 + classify_taxonomy_tier23
    so artefact check, ontology, and tier1 run concurrently via asyncio.gather
  - Era extraction and summary generation now run concurrently (were sequential)
  - Checkpoint writes at batch boundary only, not per-conversation (I/O fix)
  - taxonomy_secondary_reference excludes primary tier1 — prevents same-domain secondary
  - chunk_text overlap seed bounds check — seeded chunk exceeding CHUNK_SIZE starts fresh
  - build_exchange_pairs returns (pairs, dropped_count) — orphaned messages now logged
  - Summary prompt includes positive example for more consistent local model output
  - Routing knowledge:True fail-safe default explicitly documented

ARCHITECTURE:
  - Quality gate: conversation-level, fails closed, samples full conversation
  - Classification: 3 focused LLM calls (ontology+source_type / taxonomy / routing)
  - Taxonomy: two-call — tier1 first, then tier2/3 with narrowed options
  - Fully constrained tier1 → tier2 → tier3 taxonomy with defined value lists
  - Gnostic ontology with examples in prompt for reliable local model output
  - Era tagging: timestamp-derived + regex-gated LLM temporal extraction
  - Reinforcement: merges and upgrades metadata on similar existing entries
  - Artefact detection: LLM-based not just regex
  - Cross-reference pass: exact pair_idx matching, batch-indexed by topic
  - Controlled batch concurrency: processes in batches not all at once
  - Summaries stored in col_summaries not inline metadata
  - Full validation of all classified fields against allowed lists

USAGE:
    python ingest_chatgpt_v4.py --input "C:/path/to/conversations.json"
    python ingest_chatgpt_v4.py --input "C:/path/conversations*.json" --wipe
    python ingest_chatgpt_v4.py --input "C:/path/conversations.json" --limit 10

WORKFLOW:
    1. Test with --limit 10 first, check output and log file
    2. Run full ingest with --wipe to replace old data
    3. Run reclassify.py for contradiction detection
    4. Admin panel → Manage → Rebuild Summaries
"""

import json
import argparse
import glob
import logging
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
CHROMA_PATH   = "./chroma_db"
EMBED_MODEL   = "nomic-ai/nomic-embed-text-v1"
CHUNK_SIZE    = 800
CHUNK_OVERLAP = 100
BATCH_SIZE    = 10   # conversations processed per batch
CONCURRENCY   = 4    # parallel LLM calls within a batch

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/api/chat"
MODEL      = os.getenv("MODEL_FAST", "gemma2:27b")

REINFORCEMENT_THRESHOLD = 0.35  # increment count on existing entry
DEDUP_THRESHOLD         = 0.25  # skip entirely — true duplicate


# ── Logging setup ─────────────────────────────────────────────────────────────
# File: everything (DEBUG+). Console: warnings and above only.
_log_path = Path(f"ingest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

_file_handler    = logging.FileHandler(_log_path, encoding="utf-8")
_console_handler = logging.StreamHandler()

_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

_console_handler.setLevel(logging.WARNING)
_console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

log = logging.getLogger("lucchese_ingest")
log.setLevel(logging.DEBUG)
log.addHandler(_file_handler)
log.addHandler(_console_handler)


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

VALID_TIER1 = list(TAXONOMY.keys())

# Explicit safe defaults per tier1.
# Never rely on list ordering — define intent explicitly.
TIER_SAFE_DEFAULTS: dict[str, tuple[str, str, str]] = {
    "technology": ("technology", "computing",    "software"),
    "health":     ("health",     "training",     "technique"),
    "finance":    ("finance",    "money",        "budgeting"),
    "business":   ("business",   "operations",   "systems"),
    "society":    ("society",    "culture",      "history"),
    "science":    ("science",    "research",     "methodology"),
    "philosophy": ("philosophy", "epistemology", "knowledge"),
    "creative":   ("creative",   "content",      "writing"),
    "personal":   ("personal",   "identity",     "values"),
    "lucchese":   ("lucchese",   "system",       "architecture"),
}

def valid_tier2(t1: str) -> list:
    return list(TAXONOMY.get(t1, {}).keys())

def valid_tier3(t1: str, t2: str) -> list:
    return TAXONOMY.get(t1, {}).get(t2, [])

def validate_tier(t1: str, t2: str, t3: str, context: str = "") -> tuple[str, str, str]:
    """
    Validate tier values against taxonomy.
    Logs every correction with original and replacement — no silent failures.
    Uses explicit per-tier1 safe defaults, not index-zero fallback.
    """
    original = (t1, t2, t3)

    if t1 not in VALID_TIER1:
        safe = TIER_SAFE_DEFAULTS["personal"]
        log.warning(
            f"VALIDATE_TIER [{context}]: t1 '{t1}' not in taxonomy "
            f"→ defaulting to full safe ({safe[0]}, {safe[1]}, {safe[2]})"
        )
        return safe

    t2_options = valid_tier2(t1)
    if t2 not in t2_options:
        safe_t2 = TIER_SAFE_DEFAULTS.get(t1, (t1, t2_options[0] if t2_options else "general", "general"))[1]
        log.warning(
            f"VALIDATE_TIER [{context}]: t2 '{t2}' invalid for t1='{t1}' "
            f"→ '{safe_t2}' (valid: {t2_options})"
        )
        t2 = safe_t2

    t3_options = valid_tier3(t1, t2)
    if t3 not in t3_options:
        safe_t3 = TIER_SAFE_DEFAULTS.get(t1, (t1, t2, t3_options[0] if t3_options else "general"))[2]
        log.warning(
            f"VALIDATE_TIER [{context}]: t3 '{t3}' invalid for t1='{t1}' t2='{t2}' "
            f"→ '{safe_t3}' (valid: {t3_options})"
        )
        t3 = safe_t3

    if (t1, t2, t3) != original:
        log.info(f"VALIDATE_TIER [{context}]: {original} → ({t1}, {t2}, {t3})")

    return t1, t2, t3


def taxonomy_tier1_prompt_options() -> str:
    """Short tier1-only reference for the first taxonomy call."""
    return ", ".join(VALID_TIER1)


def taxonomy_tier2_reference(tier1: str) -> str:
    """Full tier2+tier3 options for a specific tier1. Used in second taxonomy call.
    Context window cost: ~20-40 tokens instead of ~500+ for full taxonomy."""
    t2s = TAXONOMY.get(tier1, {})
    lines = []
    for t2, t3s in t2s.items():
        lines.append(f"  {t2} → [{', '.join(t3s)}]")
    return "\n".join(lines)


def taxonomy_secondary_reference(exclude_tier1: str = "") -> str:
    """Condensed tier1→[tier2 list] reference for secondary path classification.
    Excludes the primary tier1 — prevents Gemma picking same domain for both paths.
    No tier3 — keeps the secondary prompt tight."""
    lines = []
    for t1, t2s in TAXONOMY.items():
        if t1 == exclude_tier1:
            continue
        lines.append(f"  {t1} → [{', '.join(t2s.keys())}]")
    return "\n".join(lines)


# ── Gnostic ontology ──────────────────────────────────────────────────────────
ONTOLOGY_CLASSES = ["gnosis", "episteme", "pistis", "doxa", "logos", "techne"]
VALID_SOURCE_TYPES = ["self", "dialogue", "received", "generated"]

# Explicit upgrade priority — higher number wins.
# Replaces ad-hoc hardcoded class name checks in check_and_reinforce.
# gnosis (lived it) > pistis (believes it) > techne (can do it) > logos (understands it)
# > episteme (studied it) > doxa (heard it) > unknown (classification failed)
ONTOLOGY_PRIORITY: dict[str, int] = {
    "gnosis":   6,
    "pistis":   5,
    "techne":   4,
    "logos":    3,
    "episteme": 2,
    "doxa":     1,
    "unknown":  0,
}


# ── ChromaDB setup ────────────────────────────────────────────────────────────
def get_collections():
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL,
        trust_remote_code=True  # required by nomic-embed-text-v1 — accepted risk for local personal use
    )
    client        = chromadb.PersistentClient(path=CHROMA_PATH)
    col_knowledge = client.get_or_create_collection("knowledge",  embedding_function=ef)
    col_facts     = client.get_or_create_collection("facts",      embedding_function=ef)
    col_style     = client.get_or_create_collection("style",      embedding_function=ef)
    col_summaries = client.get_or_create_collection("summaries",  embedding_function=ef)
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
                overlap_seed = current[-overlap:].strip()
                seeded = (overlap_seed + " " + sentence).strip()
                # bounds check: if seed + sentence exceeds size, start fresh
                # (overlap_seed ~100 chars + large sentence can silently blow the limit)
                current = seeded if len(seeded) <= size else sentence
            else:
                current = sentence

    if current:
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


def build_exchange_pairs(messages: list) -> tuple[list, int]:
    """
    Returns (pairs, dropped_count).
    dropped_count = number of orphaned assistant messages silently lost in v4.
    Caller logs dropped count with conv_id context.
    """
    pairs   = []
    dropped = 0
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
        elif msg["role"] == "assistant":
            # orphaned assistant message — no preceding user message
            # common in exports with regenerated responses or system injections
            dropped += 1
        i += 1
    return pairs, dropped


# ── LLM call (with retry) ────────────────────────────────────────────────────
# Semaphore created in main() and injected — not at module level (audit fix #11).
# Access via module-level reference set during startup.
_semaphore: asyncio.Semaphore | None = None

async def llm_call(client: httpx.AsyncClient, prompt: str, max_tokens: int = 100) -> str:
    """
    Exponential backoff: up to 3 attempts before returning empty string.
    Swallowing silently was masking Ollama timeouts and corrupting classifications.
    """
    assert _semaphore is not None, "llm_call called before semaphore initialised"
    async with _semaphore:
        for attempt in range(3):
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
                log.warning(f"LLM call attempt {attempt + 1}/3 failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)  # 1s, 2s
        log.error("LLM call failed after 3 attempts — returning empty string")
        return ""

def safe_json(text: str) -> dict:
    try:
        clean = re.sub(r"```json|```", "", text).strip()
        clean = re.sub(r",\s*([}\]])", r"\1", clean)
        return json.loads(clean)
    except Exception:
        log.warning(f"safe_json parse failure — raw: '{text[:120]}'")
        return {}


# ── Quality gate (fails closed, samples full conversation) ────────────────────
def sample_pairs_for_gate(pairs: list, max_samples: int = 6) -> list:
    """
    Sample from start, middle, and end of conversation.
    v3 only looked at pairs[:6] — missed depth that develops in long conversations.
    """
    n = len(pairs)
    if n <= max_samples:
        return pairs

    # Distribute: 2 from start, 2 from middle, 2 from end
    indices: list[int] = []
    indices += list(range(0, min(2, n)))
    mid = n // 2
    indices += [i for i in [mid - 1, mid] if 0 <= i < n]
    indices += list(range(max(0, n - 2), n))

    # Deduplicate while preserving order, cap at max_samples
    seen: set[int] = set()
    result: list[int] = []
    for idx in indices:
        if idx not in seen:
            seen.add(idx)
            result.append(idx)
        if len(result) >= max_samples:
            break

    return [pairs[i] for i in sorted(result)]


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

Sampled exchanges ({n_sampled} sampled from {n_total} total — start, middle, end):
{sample}

Reply with JSON only. If uncertain, return worth_storing: false.
{{"worth_storing": true, "reason": "one line"}}
or
{{"worth_storing": false, "reason": "one line"}}"""

async def quality_gate(client: httpx.AsyncClient, title: str, pairs: list, conv_id: str = "") -> tuple[bool, str]:
    sampled = sample_pairs_for_gate(pairs, max_samples=6)
    sample_lines = []
    for p in sampled:
        if p["user_text"]:
            sample_lines.append(f"[Alex]: {p['user_text'][:250]}")
        if p["assistant_text"]:
            sample_lines.append(f"[ChatGPT]: {p['assistant_text'][:200]}")

    prompt = QUALITY_PROMPT.format(
        title     = title,
        n_sampled = len(sampled),
        n_total   = len(pairs),
        sample    = "\n\n".join(sample_lines),
    )
    response = await llm_call(client, prompt, max_tokens=60)
    result   = safe_json(response)

    worth  = bool(result.get("worth_storing", False))
    reason = result.get("reason", "parse failed — skipped")

    log.info(f"GATE [{conv_id}] title='{title[:60]}' worth={worth} reason='{reason}'")
    return worth, reason


# ── Ontology + source_type classification ─────────────────────────────────────
# source_type moved here from routing — both are epistemological concerns,
# not storage routing concerns. One focused LLM call for both.
ONTOLOGY_PROMPT = """Classify the PRIMARY nature of this knowledge using exactly one ontology class.
Also classify the source_type — where this knowledge epistemologically originates.

Ontology classes:
  gnosis   — Direct personal experience or lived knowledge. Alex knows this because he lived it.
             Example: Alex describing his epilepsy diagnosis. Alex recounting starting PTPreps.

  episteme — Intellectual understanding through reasoning or study.
             Example: Alex reasoning through an investment decision. Engaging with how quantum computing works.

  pistis   — Belief or conviction held without direct proof.
             Example: Alex stating he believes money is a control system.

  doxa     — Received wisdom, cultural assumption, or general opinion.
             Example: Alex repeating what society broadly thinks. A generic factual AI explanation.

  logos    — Systematic understanding of how something works mechanically or structurally.
             Example: Alex asking how the nervous system works. How blockchain validation works.

  techne   — Practical skill or procedural knowledge. Knowing how to do or make something.
             Example: Alex asking how to set up a Shopify webhook. A training programme protocol.

source_type:
  self      — Alex expressing his own lived experience, opinion, or belief
  dialogue  — Knowledge that emerged through the back-and-forth exchange
  received  — Alex receiving information or explanation from the AI
  generated — Purely AI output, no personal content from Alex

[Alex]: {user_text}
[ChatGPT]: {assistant_text}

Reply with JSON only. No explanation. No preamble.
{{"ontology": "gnosis", "source_type": "self"}}

Valid ontology: gnosis, episteme, pistis, doxa, logos, techne
Valid source_type: self, dialogue, received, generated"""

async def classify_ontology_safe(
    client: httpx.AsyncClient,
    user_text: str,
    assistant_text: str,
    conv_id: str = "",
) -> tuple[str, str]:
    """
    Returns (ontology, source_type).
    On failure: ontology = "unknown" (honest), source_type = "received" (safe default).
    Logs every failure and every classification decision.
    """
    prompt   = ONTOLOGY_PROMPT.format(
        user_text      = user_text[:400],
        assistant_text = assistant_text[:300],
    )
    response = await llm_call(client, prompt, max_tokens=30)
    result   = safe_json(response)

    ontology    = result.get("ontology",    "").lower().strip()
    source_type = result.get("source_type", "").lower().strip()

    if ontology not in ONTOLOGY_CLASSES:
        log.warning(
            f"ONTOLOGY failure [{conv_id}]: raw='{response[:80]}' "
            f"extracted='{ontology}' → storing 'unknown'"
        )
        ontology = "unknown"
    else:
        log.debug(f"ONTOLOGY [{conv_id}]: ontology='{ontology}' source_type='{source_type}'")

    if source_type not in VALID_SOURCE_TYPES:
        log.warning(
            f"SOURCE_TYPE invalid [{conv_id}]: '{source_type}' → 'received'"
        )
        source_type = "received"

    return ontology, source_type


# ── Taxonomy classification — split into two independent async functions ───────
# This enables artefact check, ontology, and tier1 to run concurrently via gather.
# tier23 only runs after tier1 is known and after artefact check passes.

TAXONOMY_TIER1_PROMPT = """Classify this conversation into exactly one subject area.

Valid categories: {tier1_options}

[Alex]: {user_text}
[ChatGPT]: {assistant_text}

Reply with one word only — the category name. No punctuation. No explanation."""

TAXONOMY_TIER23_PROMPT = """This conversation falls under "{tier1}". Classify it further.

Available paths for {tier1}:
{tier2_ref}

[Alex]: {user_text}
[ChatGPT]: {assistant_text}

If this genuinely spans a second subject domain, choose SECONDARY tier1+tier2 from:
{secondary_ref}

Reply with JSON only:
{{
  "primary_tier2": "...",
  "primary_tier3": "...",
  "secondary_tier1": "",
  "secondary_tier2": "",
  "secondary_tier3": "",
  "is_personal": true
}}

is_personal = true only if this conversation is specifically about Alex's own life, opinions, or situation.
Leave secondary fields as empty strings if no genuine second domain applies."""

async def classify_taxonomy_tier1(
    client: httpx.AsyncClient,
    user_text: str,
    assistant_text: str,
    conv_id: str = "",
) -> str:
    """
    Returns validated tier1 string only.
    Run concurrently with is_artefact and classify_ontology_safe via asyncio.gather.
    """
    prompt = TAXONOMY_TIER1_PROMPT.format(
        tier1_options  = taxonomy_tier1_prompt_options(),
        user_text      = user_text[:400],
        assistant_text = assistant_text[:250],
    )
    _response = await llm_call(client, prompt, max_tokens=10)
    t1_raw = _response.lower().strip().split()[0] if _response.strip() else ""

    if t1_raw not in VALID_TIER1:
        safe = TIER_SAFE_DEFAULTS["personal"]
        log.warning(
            f"TAXONOMY tier1 failure [{conv_id}]: raw='{t1_raw}' "
            f"→ defaulting to '{safe[0]}'"
        )
        return safe[0]

    log.debug(f"TAXONOMY tier1 [{conv_id}]: '{t1_raw}'")
    return t1_raw


async def classify_taxonomy_tier23(
    client: httpx.AsyncClient,
    t1_raw: str,
    user_text: str,
    assistant_text: str,
    conv_id: str = "",
) -> dict:
    """
    Takes validated tier1 string, returns full taxonomy dict.
    Run after tier1 is known. Secondary reference excludes primary tier1
    to prevent Gemma classifying same domain for both paths.
    """
    # If tier1 fell back to personal default, use its safe defaults directly
    if t1_raw not in VALID_TIER1:
        safe = TIER_SAFE_DEFAULTS["personal"]
        return {
            "primary_tier1":   safe[0],
            "primary_tier2":   safe[1],
            "primary_tier3":   safe[2],
            "secondary_tier1": "",
            "secondary_tier2": "",
            "secondary_tier3": "",
            "is_personal":     "false",
        }

    prompt = TAXONOMY_TIER23_PROMPT.format(
        tier1          = t1_raw,
        tier2_ref      = taxonomy_tier2_reference(t1_raw),
        secondary_ref  = taxonomy_secondary_reference(exclude_tier1=t1_raw),
        user_text      = user_text[:400],
        assistant_text = assistant_text[:250],
    )
    response = await llm_call(client, prompt, max_tokens=120)
    result   = safe_json(response)

    pt1, pt2, pt3 = validate_tier(
        t1_raw,
        result.get("primary_tier2",  TIER_SAFE_DEFAULTS[t1_raw][1]),
        result.get("primary_tier3",  TIER_SAFE_DEFAULTS[t1_raw][2]),
        context = f"{conv_id} primary",
    )

    st1 = result.get("secondary_tier1", "")
    st2 = result.get("secondary_tier2", "")
    st3 = result.get("secondary_tier3", "")
    if st1:
        st1, st2, st3 = validate_tier(st1, st2, st3, context=f"{conv_id} secondary")

    log.debug(
        f"TAXONOMY [{conv_id}]: primary={pt1}/{pt2}/{pt3} "
        f"secondary={st1 or 'none'}/{st2}/{st3}"
    )

    return {
        "primary_tier1":   pt1,
        "primary_tier2":   pt2,
        "primary_tier3":   pt3,
        "secondary_tier1": st1,
        "secondary_tier2": st2,
        "secondary_tier3": st3,
        "is_personal":     str(result.get("is_personal", False)).lower(),
    }


# ── Collection routing (knowledge / facts / style / engagement only) ──────────
# source_type removed — now classified in ontology call where it belongs.
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
  "engagement": "active"
}}"""

async def classify_routing(
    client: httpx.AsyncClient,
    user_text: str,
    assistant_text: str,
    conv_id: str = "",
) -> dict:
    prompt   = ROUTING_PROMPT.format(
        user_text      = user_text[:400],
        assistant_text = assistant_text[:250],
    )
    response = await llm_call(client, prompt, max_tokens=60)
    result   = safe_json(response)

    engagement = result.get("engagement", "passive")
    if engagement not in ("active", "passive"):
        log.warning(f"ROUTING invalid engagement [{conv_id}]: '{engagement}' → 'passive'")
        engagement = "passive"

    routing = {
        # Intentional fail-safe: on routing parse failure, default to storing in knowledge.
        # Parse failures are logged by safe_json — check log for frequency after test run.
        "knowledge":  bool(result.get("knowledge", True)),
        "facts":      bool(result.get("facts",     False)),
        "style":      bool(result.get("style",     False)),
        "engagement": engagement,
    }
    log.debug(f"ROUTING [{conv_id}]: {routing}")
    return routing


# ── Artefact detection (LLM-based) ────────────────────────────────────────────
ARTEFACT_PROMPT = """Is this user message purely a one-off creative or generation task with no personal discussion?

Examples of artefacts: generate an image, make this less blurry, write me a tagline,
create a logo, write a title for a video, generate a poem.

Not artefacts: asking about a topic, expressing an opinion, discussing a plan,
requesting analysis or explanation, even if it results in creative output.

[Alex]: {user_text}

Reply with one word only: yes or no"""

async def is_artefact(client: httpx.AsyncClient, user_text: str) -> bool:
    artefact_signals = [
        r'\bgenerate\b.{0,20}\bimage\b',
        r'\bmake.{0,20}(less blurry|clearer|sharper)\b',
        r'\bcreate\b.{0,20}\b(logo|banner|thumbnail|image)\b',
    ]
    if any(re.search(p, user_text.lower()) for p in artefact_signals):
        return True
    prompt   = ARTEFACT_PROMPT.format(user_text=user_text[:300])
    response = await llm_call(client, prompt, max_tokens=5)
    return response.lower().strip().startswith("yes")


# ── Era temporal extraction ───────────────────────────────────────────────────
# Tightened signal list — removed "in my" (matches "in my opinion", "in my bag", etc.)
# and "at the time" (too context-dependent to be reliable without the surrounding text).
TEMPORAL_SIGNALS = [
    "years ago", "back in", "when i was",
    "a few years", "decade ago",
    "growing up", "as a kid", "as a child", "in the past",
    "back then",
]

ERA_PROMPT = """Does this text contain a reference to a specific time period or relative time?
Examples: "10 years ago", "back in 2019", "when I was younger", "in my early twenties"

Text: {text}

If yes, estimate the approximate year being referenced based on context clues.
Reply with JSON only:
{{"has_time_ref": true, "approximate_year": 2015}}
or
{{"has_time_ref": false, "approximate_year": null}}"""

async def extract_era_mention(client: httpx.AsyncClient, pairs: list) -> tuple[bool, int | None]:
    """
    v3 bug: only scanned first 5 pairs. Temporal references appear throughout
    conversations, not just at the start. v4 scans ALL user messages.

    Audit fix: no longer truncates from position 0. Finds the first temporal
    signal match and passes a 1000-char window around that position — so the LLM
    sees the context around the actual reference, not unrelated text at the start.
    """
    all_user_text = " ".join(p["user_text"] for p in pairs)
    t = all_user_text.lower()

    match_pos = -1
    for sig in TEMPORAL_SIGNALS:
        idx = t.find(sig)
        if idx != -1 and (match_pos == -1 or idx < match_pos):
            match_pos = idx

    if match_pos == -1:
        return False, None

    # Window centred on first match — not sliced from position 0
    window_start = max(0, match_pos - 200)
    text_window  = all_user_text[window_start:window_start + 1000]

    prompt   = ERA_PROMPT.format(text=text_window)
    response = await llm_call(client, prompt, max_tokens=40)
    result   = safe_json(response)

    has_ref = result.get("has_time_ref", False)
    year    = result.get("approximate_year", None)

    if isinstance(year, int) and 1980 <= year <= datetime.now().year:
        return has_ref, year
    return has_ref, None


# ── Per-conversation summary → col_summaries ──────────────────────────────────
SUMMARY_PROMPT = """Write one sentence describing this conversation and what it reveals about Alex.
Be specific about the actual topic and what Alex's engagement shows about his thinking or situation.
Do not start with "Alex" or "This conversation". Start with the topic itself.
Example of a good summary: "Sub-niches of personal training explored through questions about specialisation and client acquisition strategies, showing Alex actively building out his PT business model."

Title: {title}
Exchanges ({n} total, sample below):
{sample}

One sentence only:"""

async def generate_summary(
    client: httpx.AsyncClient,
    conv_id: str,
    title: str,
    pairs: list,
    col_summaries,
) -> str:
    sample = "\n".join([
        f"[Alex]: {p['user_text'][:150]}\n[ChatGPT]: {p['assistant_text'][:100]}"
        for p in sample_pairs_for_gate(pairs, max_samples=5)
    ])
    prompt  = SUMMARY_PROMPT.format(title=title, n=len(pairs), sample=sample)
    summary = (await llm_call(client, prompt, max_tokens=80)).strip()

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
    """
    Synchronous — always call via: await asyncio.to_thread(check_and_reinforce, ...)
    Blocking ChromaDB calls inside async context will stall the entire event loop.

    Returns True if entry was duplicate or reinforced (caller should skip upsert).
    Returns False if this is genuinely new content (caller should store it).

    Ontology upgrade uses ONTOLOGY_PRIORITY — higher priority class always wins,
    regardless of which specific class it is. No hardcoded class name checks.
    """
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
            log.debug(f"REINFORCE: true duplicate (dist={dist:.3f}), skipping")
            return True

        if dist < REINFORCEMENT_THRESHOLD:
            existing_id   = results["ids"][0][0]
            existing_meta = dict(results["metadatas"][0][0])
            count = int(existing_meta.get("reinforcement_count", "1")) + 1

            # Taxonomy upgrade: fill in missing paths
            if new_meta.get("primary_tier1") and not existing_meta.get("primary_tier1"):
                existing_meta["primary_tier1"] = new_meta["primary_tier1"]
                existing_meta["primary_tier2"] = new_meta["primary_tier2"]
                existing_meta["primary_tier3"] = new_meta["primary_tier3"]
            if new_meta.get("secondary_tier1") and not existing_meta.get("secondary_tier1"):
                existing_meta["secondary_tier1"] = new_meta["secondary_tier1"]
                existing_meta["secondary_tier2"] = new_meta["secondary_tier2"]
                existing_meta["secondary_tier3"] = new_meta["secondary_tier3"]

            # Ontology upgrade: use priority hierarchy — higher priority always wins.
            # Previously used hardcoded class name checks which had gaps (e.g. logos → gnosis never fired).
            new_ontology      = new_meta.get("ontology", "")
            existing_ontology = existing_meta.get("ontology", "unknown")
            new_priority      = ONTOLOGY_PRIORITY.get(new_ontology, -1)
            existing_priority = ONTOLOGY_PRIORITY.get(existing_ontology, 0)

            if new_priority < 0:
                log.warning(
                    f"REINFORCE: skipping ontology upgrade for id={existing_id} "
                    f"— new ontology '{new_ontology}' not in ONTOLOGY_PRIORITY"
                )
            elif new_priority > existing_priority:
                log.info(
                    f"REINFORCE: upgrading ontology for id={existing_id} "
                    f"'{existing_ontology}' (priority {existing_priority}) "
                    f"→ '{new_ontology}' (priority {new_priority})"
                )
                existing_meta["ontology"] = new_ontology

            existing_meta["reinforcement_count"] = str(count)
            existing_meta["last_reinforced"]     = datetime.now(timezone.utc).isoformat()

            collection.update(ids=[existing_id], metadatas=[existing_meta])
            log.debug(
                f"REINFORCE: incremented id={existing_id} "
                f"count={count} dist={dist:.3f}"
            )
            return True

    except Exception as e:
        log.error(f"REINFORCE error: {e}")
    return False  # fails open — better to store than lose new content


# ── Process single conversation ───────────────────────────────────────────────
async def process_conversation(
    conv: dict,
    client: httpx.AsyncClient,
    col_knowledge,
    col_facts,
    col_style,
    col_summaries,
    stats: dict,
    increment_stat,
) -> list:

    conv_id = conv.get("id") or conv.get("conversation_id", str(uuid.uuid4()))
    title   = conv.get("title", "Untitled")
    created = parse_timestamp(conv.get("create_time"))
    mapping = conv.get("mapping", {})

    if not mapping:
        await increment_stat("skipped")
        log.debug(f"SKIP [{conv_id}]: no mapping")
        return []

    messages       = extract_messages(mapping)
    pairs, dropped = build_exchange_pairs(messages)

    if dropped:
        log.debug(f"build_exchange_pairs [{conv_id}]: {dropped} orphaned assistant message(s) dropped")

    if not pairs:
        await increment_stat("skipped")
        log.debug(f"SKIP [{conv_id}]: no exchange pairs")
        return []

    # ── Quality gate — fails closed ───────────────────────────────────────────
    worth, reason = await quality_gate(client, title, pairs, conv_id=conv_id)
    if not worth:
        await increment_stat("gated_out")
        print(f"  ✗ [{title[:55]}] — {reason}")
        return []

    # ── Conversation-level metadata ───────────────────────────────────────────
    conv_year = year_from_iso(created) if created else datetime.now().year
    conv_era  = get_era_from_year(conv_year)

    # Fix #5: era extraction and summary are independent — run concurrently
    (has_era_ref, ref_year), conv_summary = await asyncio.gather(
        extract_era_mention(client, pairs),
        generate_summary(client, conv_id, title, pairs, col_summaries),
    )
    referenced_era = get_era_from_year(ref_year) if ref_year else ""

    print(f"  ✓ [{title[:55]}] {conv_era} | {reason}")
    log.info(f"PROCESSING [{conv_id}] title='{title}' era={conv_era} pairs={len(pairs)}")

    passive_entries = []

    # ── Process each exchange pair ────────────────────────────────────────────
    for j, pair in enumerate(pairs):
        user_text      = pair["user_text"].strip()
        assistant_text = pair["assistant_text"].strip()
        if not user_text:
            continue

        # Fix #3: minimum content floor — skip noise before any LLM calls fired
        if len(user_text.split()) < 5 and len(assistant_text.split()) < 20:
            log.debug(f"SKIP exchange {j} [{conv_id}] — below minimum content threshold")
            continue

        # Fix #4: artefact check, ontology, and taxonomy tier1 are all independent.
        # Run concurrently — saves ~2 sequential LLM round-trips per non-artefact exchange.
        artefact_result, (ontology_class, source_type), t1_raw = await asyncio.gather(
            is_artefact(client, user_text),
            classify_ontology_safe(client, user_text, assistant_text, conv_id=conv_id),
            classify_taxonomy_tier1(client, user_text, assistant_text, conv_id=conv_id),
        )

        # ── Artefact branch ───────────────────────────────────────────────────
        if artefact_result:
            artefact_meta = {
                "source":              "chatgpt",
                "conv_id":             conv_id,
                "title":               title,
                "created_at":          created,
                "era":                 conv_era,
                "pair_idx":            str(j),
                "type":                "artefact",
                "ontology":            "techne",
                "source_type":         "generated",
                "engagement":          "passive",  # artefacts are definitionally passive
                "is_personal":         "false",
                "primary_tier1":       "creative",
                "primary_tier2":       "content",
                "primary_tier3":       "writing",
                "secondary_tier1":     "",
                "secondary_tier2":     "",
                "secondary_tier3":     "",
                "reinforcement_count": "1",
                "last_reinforced":     created or datetime.now(timezone.utc).isoformat(),
                "cross_referenced":    "false",
                "has_era_mention":     "false",
                "referenced_era":      "",
            }
            if not await asyncio.to_thread(check_and_reinforce, user_text, col_facts, artefact_meta):
                col_facts.upsert(
                    ids       = [f"cgpt_artefact_{conv_id}_{j}"],
                    documents = [user_text],
                    metadatas = [artefact_meta],
                )
            await increment_stat("artefacts")
            continue

        # ── Non-artefact: tier1 known, run tier23 and routing concurrently ────
        taxonomy, routing = await asyncio.gather(
            classify_taxonomy_tier23(client, t1_raw, user_text, assistant_text, conv_id=conv_id),
            classify_routing(client, user_text, assistant_text, conv_id=conv_id),
        )

        base_meta = {
            "source":              "chatgpt",
            "conv_id":             conv_id,
            "title":               title,
            "created_at":          created,
            "conv_year":           str(conv_year),
            "era":                 conv_era,
            "pair_idx":            str(j),
            "has_era_mention":     str(has_era_ref).lower(),
            "referenced_era":      referenced_era,
            "ontology":            ontology_class,
            "source_type":         source_type,
            "engagement":          routing["engagement"],
            "is_personal":         taxonomy["is_personal"],
            "primary_tier1":       taxonomy["primary_tier1"],
            "primary_tier2":       taxonomy["primary_tier2"],
            "primary_tier3":       taxonomy["primary_tier3"],
            "secondary_tier1":     taxonomy["secondary_tier1"],
            "secondary_tier2":     taxonomy["secondary_tier2"],
            "secondary_tier3":     taxonomy["secondary_tier3"],
            "category":            taxonomy["primary_tier1"],  # backwards compat — remove once retrieval.py migrated to primary_tier1
            "reinforcement_count": "1",
            "last_reinforced":     created or datetime.now(timezone.utc).isoformat(),
            "cross_referenced":    "false",
        }

        # ── knowledge ─────────────────────────────────────────────────────────
        if routing["knowledge"]:
            exchange_text = f"[Alex]: {user_text}\n\n[ChatGPT]: {assistant_text}"
            for k, chunk in enumerate(chunk_text(exchange_text)):
                chunk_meta = {**base_meta, "type": "knowledge", "chunk_idx": str(k)}
                if not await asyncio.to_thread(check_and_reinforce, chunk, col_knowledge, chunk_meta):
                    col_knowledge.upsert(
                        ids       = [f"cgpt_know_{conv_id}_{j}_{k}"],
                        documents = [chunk],
                        metadatas = [chunk_meta],
                    )
                    await increment_stat("knowledge")

        # ── facts ─────────────────────────────────────────────────────────────
        if routing["facts"] and len(user_text) >= 30:
            fact_meta = {**base_meta, "type": "fact"}
            if not await asyncio.to_thread(check_and_reinforce, user_text, col_facts, fact_meta):
                col_facts.upsert(
                    ids       = [f"cgpt_fact_{conv_id}_{j}"],
                    documents = [user_text],
                    metadatas = [fact_meta],
                )
                await increment_stat("facts")

        # ── style ─────────────────────────────────────────────────────────────
        if routing["style"] and len(user_text) >= 60:
            style_meta = {**base_meta, "type": "style"}
            if not await asyncio.to_thread(check_and_reinforce, user_text, col_style, style_meta):
                col_style.upsert(
                    ids       = [f"cgpt_style_{conv_id}_{j}"],
                    documents = [user_text],
                    metadatas = [style_meta],
                )
                await increment_stat("style")

        # ── track passive entries ─────────────────────────────────────────────
        if routing["engagement"] == "passive":
            passive_entries.append({
                "conv_id":       conv_id,
                "pair_idx":      j,
                "user_text":     user_text,
                "primary_tier1": taxonomy["primary_tier1"],
                "primary_tier2": taxonomy["primary_tier2"],
            })

    await increment_stat("processed")
    return passive_entries


# ── Cross-reference pass ──────────────────────────────────────────────────────
async def cross_reference_pass(passive_entries: list, col_knowledge, col_facts):
    if not passive_entries:
        print("\nNo passive entries to cross-reference.")
        return

    print(f"\nCross-referencing {len(passive_entries)} passive entries...")
    log.info(f"CROSS_REF: starting pass on {len(passive_entries)} passive entries")

    upgraded = 0
    for i, entry in enumerate(passive_entries):
        if i > 0 and i % 100 == 0:
            log.info(f"CROSS_REF: progress {i}/{len(passive_entries)} — {upgraded} upgraded so far")
            print(f"  Cross-ref progress: {i}/{len(passive_entries)}...")
        query = f"{entry['primary_tier1']} {entry['primary_tier2']} {entry['user_text'][:200]}"
        try:
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

            # Fetch all knowledge entries for this conv_id
            know_results = col_knowledge.get(
                where   = {"conv_id": entry["conv_id"]},
                include = ["metadatas"],
            )
            if not know_results["ids"]:
                continue

            ids_to_update   = []
            metas_to_update = []

            for eid, emeta in zip(know_results["ids"], know_results["metadatas"]):
                # v3 bug: used startswith(str(j)) which matched "1" → "10", "11", etc.
                # v4 fix: exact string equality on pair_idx field stored in metadata
                if emeta.get("pair_idx") == str(entry["pair_idx"]):
                    updated = dict(emeta)
                    updated["cross_referenced"] = "true"
                    ids_to_update.append(eid)
                    metas_to_update.append(updated)

            if ids_to_update:
                col_knowledge.update(ids=ids_to_update, metadatas=metas_to_update)
                upgraded += len(ids_to_update)
                log.debug(
                    f"CROSS_REF: upgraded {len(ids_to_update)} chunks "
                    f"conv_id={entry['conv_id']} pair_idx={entry['pair_idx']}"
                )

        except Exception as e:
            log.error(f"CROSS_REF error: {e}")

    print(f"  Cross-reference complete — {upgraded} entries upgraded")
    log.info(f"CROSS_REF: complete — {upgraded} entries upgraded")


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
            log.error(f"WIPE error '{col.name}': {e}")
            print(f"  Wipe error '{col.name}': {e}")


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    global _semaphore

    parser = argparse.ArgumentParser(description="Lucchese ChatGPT Ingest v4")
    parser.add_argument("--input",  required=True, nargs="+")
    parser.add_argument("--wipe",   action="store_true")
    parser.add_argument("--limit",  type=int, default=None, help="Test on N conversations")
    parser.add_argument("--no-checkpoint", action="store_true", help="Ignore existing checkpoint and reprocess all")
    args = parser.parse_args()

    # Fix #11: semaphore created inside async context, not at module level
    _semaphore = asyncio.Semaphore(CONCURRENCY)

    # Fix #10: stats protected by lock — concurrent coroutines all write to this dict
    stats_lock = asyncio.Lock()
    stats = {
        "processed": 0, "skipped": 0, "gated_out": 0,
        "knowledge": 0, "facts":   0, "style":     0, "artefacts": 0,
    }

    async def increment_stat(key: str, n: int = 1):
        async with stats_lock:
            stats[key] += n

    input_files = []
    for pattern in args.input:
        expanded = glob.glob(pattern)
        input_files.extend(expanded if expanded else [pattern])
    input_files = sorted(set(input_files))

    print(f"\n{'─'*60}")
    print(f"Lucchese ChatGPT Ingest v4")
    print(f"Model      : {MODEL}")
    print(f"Concurrency: {CONCURRENCY}")
    print(f"Batch size : {BATCH_SIZE}")
    print(f"Files      : {', '.join(input_files)}")
    print(f"Log file   : {_log_path}")
    print(f"{'─'*60}\n")

    log.info(f"=== INGEST RUN START === model={MODEL} files={input_files}")

    # Fix #6: load checkpoint
    checkpoint_path = Path("ingest_checkpoint.json")
    if not args.no_checkpoint and checkpoint_path.exists():
        processed_ids: set[str] = set(json.loads(checkpoint_path.read_text()))
        print(f"Checkpoint loaded — {len(processed_ids)} conversations already processed\n")
        log.info(f"CHECKPOINT: loaded {len(processed_ids)} previously processed IDs")
    else:
        processed_ids = set()

    # Fix #8/9: single httpx client for both health check and processing.
    # Fix #9: health check uses OLLAMA_BASE_URL, not hardcoded localhost.
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    async with httpx.AsyncClient() as client:
        try:
            await client.get(base_url, timeout=5)
            print("✓ Ollama reachable\n")
        except Exception:
            print("✗ Ollama unreachable — is it running?")
            log.error(f"Ollama unreachable at {base_url}")
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
                log.warning(f"Input file not found: {path}")
                continue
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                all_conversations.extend(data)
                print(f"Loaded {len(data)} conversations from {p.name}")

        if args.limit:
            all_conversations = all_conversations[:args.limit]
            print(f"\n[TEST MODE] Limited to {args.limit} conversations\n")

        # Filter already-processed conversations
        if processed_ids:
            before = len(all_conversations)
            all_conversations = [
                c for c in all_conversations
                if (c.get("id") or c.get("conversation_id", "")) not in processed_ids
            ]
            skipped_count = before - len(all_conversations)
            if skipped_count:
                print(f"Skipping {skipped_count} already-processed conversations\n")
                log.info(f"CHECKPOINT: skipping {skipped_count} already-processed conversations")

        total = len(all_conversations)
        print(f"\nTotal conversations to process: {total}\n")
        log.info(f"Total conversations to process: {total}")

        all_passive = []

        async def _process_with_checkpoint(conv):
            passive = await process_conversation(
                conv, client, col_knowledge, col_facts, col_style, col_summaries,
                stats, increment_stat,
            )
            # Track conv_id in memory — checkpoint file written at batch boundary, not here
            conv_id = conv.get("id") or conv.get("conversation_id", "")
            if conv_id:
                async with stats_lock:
                    processed_ids.add(conv_id)
            return passive

        for batch_start in range(0, total, BATCH_SIZE):
            batch     = all_conversations[batch_start:batch_start + BATCH_SIZE]
            batch_end = min(batch_start + BATCH_SIZE, total)
            print(f"\nBatch {batch_start+1}–{batch_end} of {total}")
            log.info(f"BATCH {batch_start+1}–{batch_end}")

            tasks   = [_process_with_checkpoint(conv) for conv in batch]
            results = await asyncio.gather(*tasks)
            for r in results:
                if r:
                    all_passive.extend(r)

            # Fix #6: write checkpoint at batch boundary, not per-conversation.
            # Reduces disk I/O significantly on large exports.
            checkpoint_path.write_text(json.dumps(list(processed_ids)))
            log.info(f"CHECKPOINT: saved {len(processed_ids)} processed IDs after batch {batch_end}")

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
    print(f"\n  Log file       : {_log_path}")
    print(f"\nNext: reclassify.py → Admin → Rebuild Summaries")
    print(f"{'─'*60}\n")

    log.info(f"=== INGEST RUN COMPLETE === stats={stats}")


if __name__ == "__main__":
    asyncio.run(main())

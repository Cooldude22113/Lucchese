"""
reclassify.py  v1
─────────────────
Classifies all unclassified col_knowledge entries and routes
appropriate entries to col_facts and col_style.

READS:   user_text_raw from metadata (NOT document — may have [prior: ...] prefix)
         assistant_excerpt from metadata (600 chars, preamble-stripped)
WRITES:  ontology, source_type, taxonomy (3-tier), engagement, is_personal
         Sets routing_done = "true" when an entry is fully classified
         Sets category = primary_tier1 for backwards compat with retrieval.py
CREATES: new entries in col_facts and col_style for routed entries

Works for both source="chatgpt" and source="grok".
Re-runnable: uses routing_done metadata field as resumption signal — safe to stop and restart.
Run after ingest, before starting the backend.

CONTRACT WITH INGEST:
  Documents in col_knowledge may contain [prior: ...] prefixes for short messages.
  Always read user_text_raw from metadata, never the document field directly.
  assistant_excerpt is metadata["assistant_excerpt"] (600 chars max).
  pair_idx is stored as a string — cast to int when sorting.

USAGE:
    python reclassify.py
    python reclassify.py --limit 50           # test on first 50 entries
    python reclassify.py --source chatgpt     # chatgpt entries only
    python reclassify.py --source grok        # grok entries only
"""

import json
import argparse
import logging
import re
import threading
import asyncio
import httpx
import os
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
CHROMA_PATH  = "./chroma_db"
EMBED_MODEL  = "nomic-ai/nomic-embed-text-v1"
BATCH_SIZE   = 20    # entries processed per gather call
CONCURRENCY  = 4     # max concurrent LLM calls

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/api/chat"
MODEL      = os.getenv("MODEL_FAST", "gemma2:27b")

# Minimum lengths for routing to facts/style collections
MIN_FACT_LEN  = 50
MIN_STYLE_LEN = 100

# Threading lock for all ChromaDB mutations.
# asyncio.Lock is NOT thread-safe from asyncio.to_thread pool.
_chroma_lock = threading.Lock()

# Semaphore set in main() after event loop starts
_semaphore: asyncio.Semaphore | None = None


# ── Logging ───────────────────────────────────────────────────────────────────
_log_path = Path(f"reclassify_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

_file_handler    = logging.FileHandler(_log_path, encoding="utf-8")
_console_handler = logging.StreamHandler()
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_console_handler.setLevel(logging.WARNING)
_console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

log = logging.getLogger("lucchese_reclassify")
log.setLevel(logging.DEBUG)
log.addHandler(_file_handler)
log.addHandler(_console_handler)


# ── Taxonomy (must stay in sync with ingest_chatgpt_v9.py) ───────────────────
TAXONOMY = {
    "technology": {
        "ai":             ["models", "architecture", "prompting", "agents", "tools", "training", "evaluation", "ethics"],
        "computing":      ["software", "operating_systems", "databases", "algorithms", "quantum", "distributed_systems"],
        "security":       ["infosec", "opsec", "privacy", "cryptography", "networks", "vulnerabilities", "authentication"],
        "web":            ["frontend", "backend", "apis", "platforms", "ecommerce", "hosting", "protocols"],
        "hardware":       ["builds", "components", "peripherals", "networking", "embedded", "mobile_devices"],
        "infrastructure": ["cloud", "servers", "devops", "monitoring", "deployment", "automation"],
    },
    "health": {
        "training":    ["programming", "technique", "recovery", "periodisation", "cardio", "mobility", "competition"],
        "bodybuilding":["hypertrophy", "cutting", "bulking", "posing", "aesthetics", "natural_vs_enhanced"],
        "martial_arts":["striking", "grappling", "conditioning", "strategy", "competition", "history"],
        "nutrition":   ["macros", "meal_timing", "cutting_diet", "bulking_diet", "food_science", "digestion"],
        "compounds":   ["anabolics", "peptides", "sarms", "harm_reduction", "protocols", "sourcing", "pct"],
        "supplements": ["nootropics", "performance", "recovery", "health_basics", "stacking", "brands"],
        "psychedelics":["psilocybin", "mdma", "lsd", "dmt", "microdosing", "therapeutic", "harm_reduction"],
        "mental":      ["psychology", "mindset", "cognitive_performance", "mental_health", "neuroscience", "habits"],
        "medical":     ["epilepsy", "diagnosis", "treatment", "medications", "conditions", "healthcare"],
    },
    "finance": {
        "money":           ["cash_flow", "budgeting", "systems", "currency", "crypto", "banking", "wealth_building"],
        "property":        ["acquisition", "deal_analysis", "development", "valuation", "rental", "commercial", "strategy"],
        "investment":      ["equities", "vehicles", "risk", "portfolio", "passive_income", "returns"],
        "business_finance":["pricing", "margins", "revenue", "costs", "funding", "accounting"],
    },
    "business": {
        "ptpreps":        ["operations", "menu", "shopify", "marketing", "customers", "subscriptions", "growth"],
        "pub":            ["development", "operations", "events", "licensing", "refurbishment", "management"],
        "consulting":     ["it_consulting", "property_consulting", "strategy", "clients", "proposals"],
        "entrepreneurship":["startups", "ideas", "validation", "growth", "competition", "pivoting"],
        "marketing":      ["content_marketing", "social_media", "branding", "copywriting", "ads", "seo", "email"],
        "operations":     ["systems", "automation", "suppliers", "logistics", "processes", "scaling"],
    },
    "society": {
        "politics":       ["uk_politics", "global_politics", "policy", "governance", "surveillance", "power_structures", "elections"],
        "economics":      ["macro", "markets", "labour", "inequality", "systems", "theory", "trade"],
        "culture":        ["history", "philosophy", "religion", "spirituality", "esoteric", "traditions"],
        "people":         ["entrepreneurs", "public_figures", "politicians", "scientists", "athletes", "artists"],
        "social_dynamics":["influence", "group_behaviour", "hierarchies", "tribalism", "communication", "persuasion"],
        "media":          ["mainstream_media", "social_media", "propaganda", "censorship", "narrative", "alternative_media"],
    },
    "science": {
        "physics":     ["quantum_mechanics", "cosmology", "relativity", "energy", "particle_physics", "space"],
        "biology":     ["genetics", "evolution", "physiology", "neuroscience", "microbiology", "ecology"],
        "chemistry":   ["organic", "biochemistry", "pharmacology", "materials", "synthesis"],
        "mathematics": ["statistics", "probability", "algorithms", "geometry", "number_theory"],
        "research":    ["methodology", "studies", "data_analysis", "peer_review", "replication"],
    },
    "philosophy": {
        "metaphysics":        ["consciousness", "reality", "free_will", "existence", "time", "identity"],
        "ethics":             ["morality", "justice", "virtue", "consequentialism", "duty", "applied_ethics"],
        "epistemology":       ["knowledge", "truth", "belief", "perception", "scepticism", "certainty"],
        "political_philosophy":["power", "freedom", "sovereignty", "justice", "rights", "authority"],
        "philosophy_of_mind": ["cognition", "qualia", "self", "perception", "language", "rationality"],
    },
    "creative": {
        "content":          ["video", "writing", "podcasting", "social_media", "scriptwriting", "storytelling"],
        "design":           ["web_design", "visual_design", "ux", "branding", "product_design"],
        "music":            ["production", "theory", "instruments", "genres", "industry", "performance"],
        "media_consumption":["film", "gaming", "books", "documentaries", "series", "podcasts"],
    },
    "personal": {
        "identity":     ["values", "beliefs", "goals", "self_concept", "growth", "purpose"],
        "relationships":["romantic", "family", "friendships", "social_circle", "conflict", "communication"],
        "lifestyle":    ["routines", "travel", "hobbies", "environment", "possessions", "time_management"],
        "history":      ["childhood", "formative_events", "decisions", "turning_points", "regrets", "achievements"],
    },
    "lucchese": {
        "system": ["architecture", "memory", "prompts", "models", "retrieval", "classification"],
        "meta":   ["conversations", "feedback", "instructions", "improvements", "testing"],
    },
}

VALID_TIER1 = list(TAXONOMY.keys())

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

ONTOLOGY_CLASSES   = ["gnosis", "episteme", "pistis", "doxa", "logos", "techne"]
VALID_SOURCE_TYPES = ["self", "dialogue", "received", "generated"]


# ── Taxonomy helpers ──────────────────────────────────────────────────────────
def valid_tier2(t1: str) -> list:
    return list(TAXONOMY.get(t1, {}).keys())

def valid_tier3(t1: str, t2: str) -> list:
    return TAXONOMY.get(t1, {}).get(t2, [])

def taxonomy_tier1_options() -> str:
    return ", ".join(VALID_TIER1)

def taxonomy_tier2_reference(t1: str) -> str:
    lines = []
    for t2, t3s in TAXONOMY.get(t1, {}).items():
        lines.append(f"  {t2} → [{', '.join(t3s)}]")
    return "\n".join(lines)

def taxonomy_secondary_reference(exclude_t1: str = "") -> str:
    lines = []
    for t1, t2s in TAXONOMY.items():
        if t1 == exclude_t1:
            continue
        lines.append(f"  {t1} → [{', '.join(t2s.keys())}]")
    return "\n".join(lines)

def validate_tier(t1: str, t2: str, t3: str, context: str = "") -> tuple[str, str, str]:
    original = (t1, t2, t3)

    if t1 not in VALID_TIER1:
        safe = TIER_SAFE_DEFAULTS["personal"]
        log.warning(f"VALIDATE_TIER [{context}]: t1 '{t1}' invalid → {safe}")
        return safe

    t2_options = valid_tier2(t1)
    if t2 not in t2_options:
        safe_t2 = TIER_SAFE_DEFAULTS[t1][1]
        log.warning(f"VALIDATE_TIER [{context}]: t2 '{t2}' invalid for '{t1}' → '{safe_t2}'")
        t2 = safe_t2

    t3_options = valid_tier3(t1, t2)
    if t3 not in t3_options:
        safe_t3 = TIER_SAFE_DEFAULTS[t1][2]
        log.warning(f"VALIDATE_TIER [{context}]: t3 '{t3}' invalid for '{t1}/{t2}' → '{safe_t3}'")
        t3 = safe_t3

    if (t1, t2, t3) != original:
        log.info(f"VALIDATE_TIER [{context}]: {original} → ({t1}, {t2}, {t3})")

    return t1, t2, t3


# ── ChromaDB setup ────────────────────────────────────────────────────────────
def get_collections():
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL,
        trust_remote_code=True
    )
    client        = chromadb.PersistentClient(path=CHROMA_PATH)
    col_knowledge = client.get_or_create_collection("knowledge", embedding_function=ef)
    col_facts     = client.get_or_create_collection("facts",     embedding_function=ef)
    col_style     = client.get_or_create_collection("style",     embedding_function=ef)
    return client, ef, col_knowledge, col_facts, col_style


# ── LLM helpers ───────────────────────────────────────────────────────────────
async def llm_call(client: httpx.AsyncClient, prompt: str, max_tokens: int = 80) -> str:
    assert _semaphore is not None, "semaphore not initialised"
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
                log.warning(f"LLM attempt {attempt+1}/3 failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
        log.error("LLM call failed after 3 attempts — returning empty string")
        return ""

def safe_json(text: str) -> dict:
    try:
        clean = re.sub(r"```json|```", "", text).strip()
        clean = re.sub(r",\s*([}\]])", r"\1", clean)
        return json.loads(clean)
    except Exception:
        pass
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            clean = re.sub(r",\s*([}\]])", r"\1", match.group(0))
            return json.loads(clean)
    except Exception:
        pass
    log.warning(f"safe_json: parse failure — '{text[:120]}'")
    return {}


# ── Classification prompts ────────────────────────────────────────────────────
_TIER1_PROMPT = """Classify this conversation into exactly one subject area.

Valid categories: {tier1_options}

[Alex]: {user_text}
[Assistant]: {assistant_excerpt}

Reply with one word only — the category name. No punctuation. No explanation."""

_TIER23_PROMPT = """This conversation falls under "{tier1}". Classify it further.

Available paths for {tier1}:
{tier2_ref}

[Alex]: {user_text}
[Assistant]: {assistant_excerpt}

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

is_personal = true only if this is specifically about Alex's own life, opinions, or situation.
Leave secondary fields as empty strings if no second domain applies."""

_ONTOLOGY_PROMPT = """Classify the primary nature of this knowledge and its epistemological source.

Ontology classes:
  gnosis   — Alex's direct personal experience or lived knowledge.
             Example: describing his epilepsy diagnosis, recounting starting PTPreps.
  episteme — Intellectual understanding through reasoning or study.
             Example: reasoning through an investment decision, how quantum computing works.
  pistis   — Belief or conviction held without direct proof.
             Example: Alex stating he believes money is a control system.
  doxa     — Received wisdom, cultural assumption, or general opinion.
             Example: repeating mainstream views, a generic factual AI explanation.
  logos    — Systematic understanding of how something works mechanically.
             Example: how the nervous system works, how blockchain validation works.
  techne   — Practical skill or procedural knowledge.
             Example: how to set up a Shopify webhook, a training programme protocol.

source_type:
  self      — Alex expressing his own lived experience, opinion, or belief
  dialogue  — Knowledge that emerged through the back-and-forth exchange
  received  — Alex receiving information or explanation from the AI
  generated — Purely AI output, no personal content from Alex

[Alex]: {user_text}
[Assistant]: {assistant_excerpt}

Reply with JSON only. No explanation.
{{"ontology": "episteme", "source_type": "received"}}

Valid ontology: gnosis, episteme, pistis, doxa, logos, techne
Valid source_type: self, dialogue, received, generated"""

_ROUTING_PROMPT = """Decide storage routing for this exchange from Alex's conversation history.

facts = true if Alex's message contains a clear statement, opinion, belief, preference, or personal fact.
        false if Alex is just issuing a task instruction with no personal content.

style = true if Alex's message shows his natural voice — direct, personal, opinionated, curious.
        false for task instructions, one-word replies, or generic prompts.

engagement = "active" if Alex is genuinely engaging — follow-up questions, pushback, opinions, depth.
           = "passive" if Alex asked once and accepted the reply with no further engagement.

[Alex]: {user_text}
[Assistant]: {assistant_excerpt}

Reply with JSON only:
{{"facts": false, "style": false, "engagement": "passive"}}"""


# ── Classification functions ──────────────────────────────────────────────────
async def _classify_tier1(
    client: httpx.AsyncClient,
    user_text: str,
    assistant_excerpt: str,
    entry_id: str,
) -> str:
    prompt   = _TIER1_PROMPT.format(
        tier1_options     = taxonomy_tier1_options(),
        user_text         = user_text[:400],
        assistant_excerpt = assistant_excerpt[:250],
    )
    response = await llm_call(client, prompt, max_tokens=10)
    t1       = response.lower().strip().split()[0] if response.strip() else ""

    if t1 not in VALID_TIER1:
        log.warning(f"TIER1 [{entry_id}]: '{t1}' not valid → 'personal'")
        return TIER_SAFE_DEFAULTS["personal"][0]

    log.debug(f"TIER1 [{entry_id}]: '{t1}'")
    return t1


async def _classify_tier23(
    client: httpx.AsyncClient,
    t1: str,
    user_text: str,
    assistant_excerpt: str,
    entry_id: str,
) -> dict:
    prompt   = _TIER23_PROMPT.format(
        tier1             = t1,
        tier2_ref         = taxonomy_tier2_reference(t1),
        secondary_ref     = taxonomy_secondary_reference(exclude_t1=t1),
        user_text         = user_text[:400],
        assistant_excerpt = assistant_excerpt[:250],
    )
    response = await llm_call(client, prompt, max_tokens=120)
    result   = safe_json(response)

    pt1, pt2, pt3 = validate_tier(
        t1,
        result.get("primary_tier2",  TIER_SAFE_DEFAULTS[t1][1]),
        result.get("primary_tier3",  TIER_SAFE_DEFAULTS[t1][2]),
        context=f"{entry_id} primary",
    )
    st1 = result.get("secondary_tier1", "")
    st2 = result.get("secondary_tier2", "")
    st3 = result.get("secondary_tier3", "")
    if st1:
        st1, st2, st3 = validate_tier(st1, st2, st3, context=f"{entry_id} secondary")

    is_personal = str(result.get("is_personal", False)).lower()

    log.debug(f"TIER23 [{entry_id}]: {pt1}/{pt2}/{pt3} secondary={st1 or 'none'}")

    return {
        "primary_tier1":   pt1,
        "primary_tier2":   pt2,
        "primary_tier3":   pt3,
        "secondary_tier1": st1,
        "secondary_tier2": st2,
        "secondary_tier3": st3,
        "is_personal":     is_personal,
    }


async def _classify_ontology(
    client: httpx.AsyncClient,
    user_text: str,
    assistant_excerpt: str,
    entry_id: str,
) -> tuple[str, str]:
    prompt   = _ONTOLOGY_PROMPT.format(
        user_text         = user_text[:400],
        assistant_excerpt = assistant_excerpt[:300],
    )
    response = await llm_call(client, prompt, max_tokens=30)
    result   = safe_json(response)

    ontology    = result.get("ontology",    "").lower().strip()
    source_type = result.get("source_type", "").lower().strip()

    if ontology not in ONTOLOGY_CLASSES:
        log.warning(f"ONTOLOGY [{entry_id}]: '{ontology}' → 'unknown'")
        ontology = "unknown"
    if source_type not in VALID_SOURCE_TYPES:
        log.warning(f"SOURCE_TYPE [{entry_id}]: '{source_type}' → 'received'")
        source_type = "received"

    log.debug(f"ONTOLOGY [{entry_id}]: '{ontology}' source='{source_type}'")
    return ontology, source_type


async def _classify_routing(
    client: httpx.AsyncClient,
    user_text: str,
    assistant_excerpt: str,
    entry_id: str,
) -> dict:
    prompt   = _ROUTING_PROMPT.format(
        user_text         = user_text[:400],
        assistant_excerpt = assistant_excerpt[:250],
    )
    response = await llm_call(client, prompt, max_tokens=40)
    result   = safe_json(response)

    engagement = result.get("engagement", "passive")
    if engagement not in ("active", "passive"):
        log.warning(f"ROUTING [{entry_id}]: engagement '{engagement}' → 'passive'")
        engagement = "passive"

    routing = {
        "facts":      bool(result.get("facts",  False)),
        "style":      bool(result.get("style",  False)),
        "engagement": engagement,
    }
    log.debug(f"ROUTING [{entry_id}]: {routing}")
    return routing


async def classify_entry(
    entry_id: str,
    meta: dict,
    client: httpx.AsyncClient,
) -> dict:
    """
    Classify one knowledge entry. Returns all fields to write plus routing flags.

    Wave 1: tier1 + ontology run concurrently (ontology doesn't need tier1 result).
    Wave 2: tier23 + routing run concurrently (tier23 needs t1, routing is independent).

    Always reads user_text_raw from metadata, never the document field.
    """
    user_text         = meta.get("user_text_raw", "").strip()
    assistant_excerpt = meta.get("assistant_excerpt", "").strip()
    assistant_length  = meta.get("assistant_length", 0)

    if not user_text:
        log.warning(f"CLASSIFY [{entry_id}]: no user_text_raw — applying defaults")
        safe = TIER_SAFE_DEFAULTS["personal"]
        return {
            "ontology":        "unknown",
            "source_type":     "received",
            "engagement":      "passive",
            "is_personal":     "false",
            "primary_tier1":   safe[0],
            "primary_tier2":   safe[1],
            "primary_tier3":   safe[2],
            "secondary_tier1": "",
            "secondary_tier2": "",
            "secondary_tier3": "",
            "category":        safe[0],
            "routing_done":    "true",
            "_facts":          False,
            "_style":          False,
        }

    # Optionally note truncation in the assistant excerpt to the prompts
    excerpt_note = ""
    if isinstance(assistant_length, int) and assistant_length > 1200:
        excerpt_note = f" [Note: full response is {assistant_length} chars; only first 600 shown]"
    assistant_ctx = assistant_excerpt + excerpt_note

    # Wave 1: tier1 and ontology are independent — run concurrently
    t1, (ontology, source_type) = await asyncio.gather(
        _classify_tier1(client, user_text, assistant_ctx, entry_id),
        _classify_ontology(client, user_text, assistant_ctx, entry_id),
    )

    # Wave 2: tier23 needs t1, routing is independent — run concurrently
    taxonomy, routing = await asyncio.gather(
        _classify_tier23(client, t1, user_text, assistant_ctx, entry_id),
        _classify_routing(client, user_text, assistant_ctx, entry_id),
    )

    return {
        "ontology":        ontology,
        "source_type":     source_type,
        "engagement":      routing["engagement"],
        "is_personal":     taxonomy["is_personal"],
        "primary_tier1":   taxonomy["primary_tier1"],
        "primary_tier2":   taxonomy["primary_tier2"],
        "primary_tier3":   taxonomy["primary_tier3"],
        "secondary_tier1": taxonomy["secondary_tier1"],
        "secondary_tier2": taxonomy["secondary_tier2"],
        "secondary_tier3": taxonomy["secondary_tier3"],
        "category":        taxonomy["primary_tier1"],  # backwards compat — retrieval.py
        "routing_done":    "true",
        "_facts":          routing["facts"],           # internal routing flag — popped before write
        "_style":          routing["style"],           # internal routing flag — popped before write
    }


# ── Write entry ───────────────────────────────────────────────────────────────
def _write_entry_sync(
    entry_id: str,
    meta: dict,
    classification: dict,
    col_knowledge,
    col_facts,
    col_style,
) -> dict:
    """
    Synchronous — always call via asyncio.to_thread.
    Updates knowledge entry, creates facts/style entries if routed.
    Returns dict of what was written: {"facts": bool, "style": bool}
    """
    user_text_raw = meta.get("user_text_raw", "")

    route_facts = classification.pop("_facts", False)
    route_style = classification.pop("_style", False)

    updated_meta = {**meta, **classification}

    # Update knowledge entry with classified fields
    with _chroma_lock:
        col_knowledge.update(
            ids       = [entry_id],
            metadatas = [updated_meta],
        )

    wrote_fact  = False
    wrote_style = False

    # Create facts entry — user_text_raw as document, full classified metadata
    if route_facts and len(user_text_raw) >= MIN_FACT_LEN:
        fact_meta = {**updated_meta, "type": "fact", "source_knowledge_id": entry_id}
        with _chroma_lock:
            col_facts.upsert(
                ids       = [f"fact_{entry_id}"],
                documents = [user_text_raw],
                metadatas = [fact_meta],
            )
        wrote_fact = True

    # Create style entry — user_text_raw as document, full classified metadata
    if route_style and len(user_text_raw) >= MIN_STYLE_LEN:
        style_meta = {**updated_meta, "type": "style", "source_knowledge_id": entry_id}
        with _chroma_lock:
            col_style.upsert(
                ids       = [f"style_{entry_id}"],
                documents = [user_text_raw],
                metadatas = [style_meta],
            )
        wrote_style = True

    return {"facts": wrote_fact, "style": wrote_style}


# ── Per-entry task ─────────────────────────────────────────────────────────────
async def process_entry(
    entry_id: str,
    meta: dict,
    client: httpx.AsyncClient,
    col_knowledge,
    col_facts,
    col_style,
) -> dict:
    """
    Returns {"facts": bool, "style": bool, "error": bool}
    Never raises — all exceptions caught and logged.
    """
    try:
        classification = await classify_entry(entry_id, meta, client)
        result = await asyncio.to_thread(
            _write_entry_sync,
            entry_id, meta, classification,
            col_knowledge, col_facts, col_style,
        )
        return {**result, "error": False}
    except Exception as e:
        import traceback
        log.error(
            f"ENTRY CRASH [{entry_id}]: {type(e).__name__}: {e}\n"
            f"{traceback.format_exc()}"
        )
        return {"facts": False, "style": False, "error": True}


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    global _semaphore

    parser = argparse.ArgumentParser(description="Lucchese Reclassify v1")
    parser.add_argument("--limit",  type=int, default=None,
                        help="Process only N entries (test mode)")
    parser.add_argument("--source", type=str, default=None,
                        help="Filter by source: chatgpt or grok")
    args = parser.parse_args()

    _semaphore = asyncio.Semaphore(CONCURRENCY)

    print(f"\n{'─'*60}")
    print(f"Lucchese Reclassify v1")
    print(f"Model       : {MODEL}")
    print(f"Concurrency : {CONCURRENCY}")
    print(f"Batch size  : {BATCH_SIZE}")
    print(f"Log         : {_log_path}")
    if args.source:
        print(f"Source      : {args.source} only")
    if args.limit:
        print(f"Limit       : {args.limit} entries [TEST MODE]")
    print(f"{'─'*60}\n")

    log.info(f"=== RECLASSIFY START === model={MODEL} source={args.source} limit={args.limit}")

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    async with httpx.AsyncClient() as client:
        try:
            await client.get(base_url, timeout=5)
            print("✓ Ollama reachable\n")
        except Exception:
            print("✗ Ollama unreachable — is it running?")
            log.error(f"Ollama unreachable at {base_url}")
            return

        _, _, col_knowledge, col_facts, col_style = get_collections()

        # ── Fetch all unclassified knowledge entries ───────────────────────────
        print("Fetching unclassified entries from col_knowledge...")

        # Build where clause — supports optional source filter
        if args.source:
            where_clause = {
                "$and": [
                    {"routing_done": {"$eq": "false"}},
                    {"source":       {"$eq": args.source}},
                ]
            }
        else:
            where_clause = {"routing_done": {"$eq": "false"}}

        FETCH_SIZE = 500
        all_ids, all_metas = [], []
        offset = 0

        while True:
            try:
                batch = col_knowledge.get(
                    where   = where_clause,
                    limit   = FETCH_SIZE,
                    offset  = offset,
                    include = ["metadatas"],
                )
            except Exception as e:
                log.error(f"Fetch error at offset {offset}: {e}")
                print(f"  Error fetching entries: {e}")
                break

            if not batch["ids"]:
                break

            all_ids.extend(batch["ids"])
            all_metas.extend(batch["metadatas"])
            offset += FETCH_SIZE
            print(f"  Fetched {len(all_ids)}...", end="\r")

        print(f"\nUnclassified entries found: {len(all_ids)}")

        if not all_ids:
            print("\nNothing to classify.")
            print("Either everything is already done (routing_done='true')")
            print("or the ingest hasn't run yet.")
            col_total = col_knowledge.count()
            print(f"\nTotal entries in col_knowledge: {col_total}")
            if col_total > 0:
                # Check a sample to diagnose
                sample = col_knowledge.get(limit=1, include=["metadatas"])
                if sample["metadatas"]:
                    rd = sample["metadatas"][0].get("routing_done", "FIELD MISSING")
                    print(f"Sample routing_done value: '{rd}'")
                    if rd == "FIELD MISSING":
                        print("routing_done field not present — entries are from old ingest format.")
                        print("Run --wipe on the ingest script and re-ingest with v9.")
            return

        if args.limit:
            all_ids   = all_ids[:args.limit]
            all_metas = all_metas[:args.limit]
            print(f"[TEST MODE] Limited to {args.limit} entries\n")

        total = len(all_ids)
        print(f"Processing {total} entries...\n")
        log.info(f"Processing {total} unclassified entries")

        stats = {
            "knowledge_updated": 0,
            "facts_created":     0,
            "style_created":     0,
            "errors":            0,
        }

        for batch_start in range(0, total, BATCH_SIZE):
            batch_end   = min(batch_start + BATCH_SIZE, total)
            batch_ids   = all_ids[batch_start:batch_end]
            batch_metas = all_metas[batch_start:batch_end]

            tasks = [
                process_entry(eid, emeta, client, col_knowledge, col_facts, col_style)
                for eid, emeta in zip(batch_ids, batch_metas)
            ]
            results = await asyncio.gather(*tasks)

            for r in results:
                stats["knowledge_updated"] += 1
                if r["facts"]:  stats["facts_created"] += 1
                if r["style"]:  stats["style_created"] += 1
                if r["error"]:  stats["errors"] += 1

            pct = batch_end / total * 100
            print(
                f"  {batch_end}/{total} ({pct:.0f}%) "
                f"| knowledge={stats['knowledge_updated']} "
                f"| facts={stats['facts_created']} "
                f"| style={stats['style_created']} "
                f"| errors={stats['errors']}"
            )
            log.info(
                f"BATCH {batch_start+1}–{batch_end} | "
                f"knowledge={stats['knowledge_updated']} "
                f"facts={stats['facts_created']} "
                f"style={stats['style_created']} "
                f"errors={stats['errors']}"
            )

    print(f"\n{'─'*60}")
    print(f"✓ Complete")
    print(f"  Knowledge updated : {stats['knowledge_updated']}")
    print(f"  Facts created     : {stats['facts_created']}")
    print(f"  Style created     : {stats['style_created']}")
    print(f"  Errors            : {stats['errors']}")
    print(f"\n  Log: {_log_path}")
    print(f"\nNext: Admin panel → Manage → Rebuild Summaries")
    print(f"{'─'*60}\n")

    log.info(f"=== RECLASSIFY COMPLETE === stats={stats}")


if __name__ == "__main__":
    asyncio.run(main())
"""
pipeline/shared.py
──────────────────
Shared utilities for the Lucchese offline ingestion pipeline.

Contains exactly:
  - Shared constants (defaults; each ingest script may override locally)
  - chunk_text       — sliding-window chunker with hash-guard (ingestgpt.py source)
  - safe_json        — LLM JSON parser with Gemma preamble fallback
  - llm_call         — async LLM call with explicit semaphore/url/model params
  - ERA_BOUNDARIES, get_era_from_year
  - TEMPORAL_SIGNALS, ERA_PROMPT, extract_era_mention
  - make_logger      — double-handler logger factory (file DEBUG, console WARNING)
  - TAXONOMY, VALID_TIER1, TIER_SAFE_DEFAULTS, validate_tier
  - sample_pairs_for_summary

Does NOT contain:
  - Any ChromaDB collection setup
  - Any ingest-specific logic (noise filters, message extraction, pair building)
  - Any ChromaDB write operations
  - Summary generation (that lives in generate_summaries.py)
  - Any argparse setup
"""

import hashlib
import json
import logging
import re
import asyncio
from datetime import datetime
from pathlib import Path

import httpx

# ── Shared constants ──────────────────────────────────────────────────────────
# Each ingest script may override these locally if needed.
CHROMA_PATH   = "./chroma_db"
EMBED_MODEL   = "nomic-ai/nomic-embed-text-v1"
CHUNK_SIZE    = 800
CHUNK_OVERLAP = 100
BATCH_SIZE    = 10
CONCURRENCY   = 4


# ── Text chunking ─────────────────────────────────────────────────────────────
# Source of truth: ingestgpt.py version (has hash-guard on final chunk).
# grok.py version lacked the hash-guard — gap closed by this merge.
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
                # bounds check: seeded chunk must not exceed size
                current = seeded if len(seeded) <= size else sentence
            else:
                current = sentence

    if current:
        chunk_hash = hashlib.md5(current.encode()).hexdigest()
        existing_hashes = {hashlib.md5(c.encode()).hexdigest() for c in chunks}
        if chunk_hash not in existing_hashes:
            chunks.append(current)

    return [c for c in chunks if len(c.strip()) > 20]


# ── JSON parsing ──────────────────────────────────────────────────────────────
def safe_json(text: str) -> dict:
    """
    Parse JSON from LLM response.
    Handles Gemma preamble pattern: "Sure! Here's the JSON: {...}"
    Strips markdown fences. Falls back to regex extraction.
    """
    try:
        clean = re.sub(r"```json|```", "", text).strip()
        clean = re.sub(r",\s*([}\]])", r"\1", clean)
        return json.loads(clean)
    except Exception:
        pass
    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            clean = re.sub(r",\s*([}\]])", r"\1", match.group(0))
            return json.loads(clean)
    except Exception:
        pass
    return {}


# ── LLM call ─────────────────────────────────────────────────────────────────
# Semaphore, url, and model are explicit parameters — not module globals.
# Each calling script passes its own _semaphore, OLLAMA_URL, and MODEL.
async def llm_call(
    client: httpx.AsyncClient,
    prompt: str,
    max_tokens: int,
    semaphore: asyncio.Semaphore,
    ollama_url: str,
    model: str,
) -> str:
    async with semaphore:
        for attempt in range(3):
            try:
                res = await client.post(
                    ollama_url,
                    json={
                        "model":    model,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream":   False,
                        "options":  {"temperature": 0, "num_predict": max_tokens},
                    },
                    timeout=90,
                )
                return res.json()["message"]["content"].strip()
            except Exception as e:
                # Caller's logger not available here — callers log on failure
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
        return ""


# ── Era boundaries ────────────────────────────────────────────────────────────
ERA_BOUNDARIES = [
    (None, 2013, "pre_divorce"),    # before parents split
    (2013, 2020, "post_divorce"),   # post-divorce to epilepsy diagnosis
    (2020, 2022, "transition"),     # diagnosis + adjustment
    (2022, 2024, "building"),       # PTPreps, Lucchese, current projects
    (2024, None, "present"),
]

def get_era_from_year(year: int) -> str:
    for start, end, label in ERA_BOUNDARIES:
        if (start is None or year >= start) and (end is None or year < end):
            return label
    return "present"


# ── Era extraction ────────────────────────────────────────────────────────────
# Function preserved here for future invocation. NOT called at ingest time
# after LC-043 — era fields ship as "unclassified" until a dedicated stage
# is specified. See LC-043 spec: "Era Extraction — Disposition".
TEMPORAL_SIGNALS = [
    "years ago", "back in", "when i was",
    "a few years", "decade ago",
    "growing up", "as a kid", "as a child",
    "in the past", "back then",
]

ERA_PROMPT = """Does this text reference a specific time period or relative time?
Examples: "10 years ago", "back in 2019", "when I was younger"

Text: {text}

Reply with JSON only:
{{"has_time_ref": true, "approximate_year": 2015}}
or
{{"has_time_ref": false, "approximate_year": null}}"""

async def extract_era_mention(
    client: httpx.AsyncClient,
    pairs: list,
    semaphore: asyncio.Semaphore,
    ollama_url: str,
    model: str,
) -> tuple[bool, int | None]:
    """
    Scans ALL user messages. Regex-gated: fires LLM only if temporal signal found.
    Windows around match position for context.

    Not invoked at ingest time per LC-043. Preserved here for future stage.
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

    window_start = max(0, match_pos - 200)
    text_window  = all_user_text[window_start:window_start + 1000]

    prompt   = ERA_PROMPT.format(text=text_window)
    response = await llm_call(client, prompt, 40, semaphore, ollama_url, model)
    result   = safe_json(response)

    has_ref = result.get("has_time_ref", False)
    year    = result.get("approximate_year", None)

    if isinstance(year, int) and 1980 <= year <= datetime.now().year:
        return has_ref, year

    return False, None


# ── Logger factory ────────────────────────────────────────────────────────────
def make_logger(name: str, log_path: Path) -> logging.Logger:
    """
    Returns a logger with two handlers:
      - File handler: DEBUG level, timestamped format
      - Console handler: WARNING level, short format

    Format is identical to the existing per-script logging setup so
    log files remain grep-compatible across all pipeline scripts.
    """
    file_handler    = logging.FileHandler(log_path, encoding="utf-8")
    console_handler = logging.StreamHandler()

    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# ── Taxonomy ──────────────────────────────────────────────────────────────────
# Moved here from reclassify.py so write_classifications.py can validate
# tier values without importing reclassify.py.
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
        "money":            ["cash_flow", "budgeting", "systems", "currency", "crypto", "banking", "wealth_building"],
        "property":         ["acquisition", "deal_analysis", "development", "valuation", "rental", "commercial", "strategy"],
        "investment":       ["equities", "vehicles", "risk", "portfolio", "passive_income", "returns"],
        "business_finance": ["pricing", "margins", "revenue", "costs", "funding", "accounting"],
    },
    "business": {
        "ptpreps":         ["operations", "menu", "shopify", "marketing", "customers", "subscriptions", "growth"],
        "pub":             ["development", "operations", "events", "licensing", "refurbishment", "management"],
        "consulting":      ["it_consulting", "property_consulting", "strategy", "clients", "proposals"],
        "entrepreneurship":["startups", "ideas", "validation", "growth", "competition", "pivoting"],
        "marketing":       ["content_marketing", "social_media", "branding", "copywriting", "ads", "seo", "email"],
        "operations":      ["systems", "automation", "suppliers", "logistics", "processes", "scaling"],
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
        "metaphysics":         ["consciousness", "reality", "free_will", "existence", "time", "identity"],
        "ethics":              ["morality", "justice", "virtue", "consequentialism", "duty", "applied_ethics"],
        "epistemology":        ["knowledge", "truth", "belief", "perception", "scepticism", "certainty"],
        "political_philosophy":["power", "freedom", "sovereignty", "justice", "rights", "authority"],
        "philosophy_of_mind":  ["cognition", "qualia", "self", "perception", "language", "rationality"],
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


def validate_tier(t1: str, t2: str, t3: str, context: str = "") -> tuple[str, str, str]:
    """Validate and coerce tier values to known-good values. Logs any corrections."""
    import logging
    _log = logging.getLogger("lucchese_pipeline")

    original = (t1, t2, t3)

    if t1 not in VALID_TIER1:
        safe = TIER_SAFE_DEFAULTS["personal"]
        _log.warning(f"VALIDATE_TIER [{context}]: t1 '{t1}' invalid -> {safe}")
        return safe

    valid_t2 = list(TAXONOMY.get(t1, {}).keys())
    if t2 not in valid_t2:
        safe_t2 = TIER_SAFE_DEFAULTS[t1][1]
        _log.warning(f"VALIDATE_TIER [{context}]: t2 '{t2}' invalid for '{t1}' -> '{safe_t2}'")
        t2 = safe_t2

    valid_t3 = TAXONOMY.get(t1, {}).get(t2, [])
    if t3 not in valid_t3:
        safe_t3 = TIER_SAFE_DEFAULTS[t1][2]
        _log.warning(f"VALIDATE_TIER [{context}]: t3 '{t3}' invalid for '{t1}/{t2}' -> '{safe_t3}'")
        t3 = safe_t3

    if (t1, t2, t3) != original:
        _log.info(f"VALIDATE_TIER [{context}]: {original} -> ({t1}, {t2}, {t3})")

    return t1, t2, t3


# ── Summary sampling ──────────────────────────────────────────────────────────
# Renamed from _sample_for_summary for clarity as a shared utility.
def sample_pairs_for_summary(pairs: list, max_samples: int = 6) -> list:
    """
    Weight toward final third of conversation — that's where Alex's actual
    positions tend to land after a long exchange, not the opening questions.
    """
    n = len(pairs)
    if n <= max_samples:
        return pairs

    # 1 from start, 1 from mid, 4 from final third
    indices = [0]
    mid = n // 2
    indices.append(mid)
    final_third_start = max(mid + 1, n - 4)
    indices += list(range(final_third_start, n))

    seen   = set()
    result = []
    for idx in indices:
        if idx not in seen and 0 <= idx < n:
            seen.add(idx)
            result.append(idx)
        if len(result) >= max_samples:
            break

    return [pairs[i] for i in sorted(result)]

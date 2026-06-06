"""
seed_profile.py
───────────────
Profile State Seeding Pipeline V3 — extended field coverage with candidate grouping.

PREREQUISITES:
  reclassify.py must have been run. col_facts must be populated with classified
  self-sourced entries before extraction will produce results.

USAGE:
  python seed_profile.py --extract
  python seed_profile.py --extract --output my_candidates.json --candidates-per-field 15
  python seed_profile.py --apply
  python seed_profile.py --apply --input my_candidates.json --api-base http://localhost:8000

WORKFLOW:
  1. Run reclassify.py (col_facts must be non-empty with source_type=self entries).
  2. Run --extract: scans col_facts, queries per extractable field, runs LLM
     extraction exhaustively, scores, groups by normalised value, writes
     profile_candidates.json (schema_version=V3).
  3. Open profile_candidates.json. For each extractable field, review top_group
     and alternative_groups. For each manual field, fill in confirmed_value
     directly. Set "action" to one of:
       "accept_top"   — use the top-ranked group's display_value (extractable only)
       "accept_other" — set confirmed_alt_index to a 0-based index into
                        alternative_groups (extractable only)
       "edit"         — set confirmed_value to your corrected value
       "skip"         — do not write this field
  4. Run --apply: reads actions, validates, PATCHes /state/profile via the API.
  5. Keep profile_candidates.json. It is the audit trail.

FIELD TYPES:
  Extractable fields — queried from ChromaDB and extracted via LLM:
    age, primary_project, active_projects, current_business, training_focus,
    current_priorities, focus_area

  Manual fields — no extraction attempted; human fills confirmed_value directly:
    active_course, course_status,
    historical_context,
"""

import json
import argparse
import asyncio
import logging
import math
import re
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
CHROMA_PATH     = os.getenv("CHROMA_PATH", "./chroma_db")
EMBED_MODEL     = "nomic-ai/nomic-embed-text-v1"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_CHAT_URL = OLLAMA_BASE_URL.rstrip("/") + "/api/chat"
MODEL           = os.getenv("MODEL_FAST", "gemma2:27b")
API_BASE        = os.getenv("LUCCHESE_API_BASE", "http://localhost:8000")
CONCURRENCY     = 4

CONTRADICTION_SCORE_GAP_THRESHOLD = 0.15

SCHEMA_VERSION       = "V3"
MAX_EVIDENCE_PER_GROUP = 5

# ── Logging ───────────────────────────────────────────────────────────────────
_log_path        = Path(f"seed_profile_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
_file_handler    = logging.FileHandler(_log_path, encoding="utf-8")
_console_handler = logging.StreamHandler()
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_console_handler.setLevel(logging.WARNING)
_console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
log = logging.getLogger("lucchese_seed_profile")
log.setLevel(logging.DEBUG)
log.addHandler(_file_handler)
log.addHandler(_console_handler)

_semaphore: asyncio.Semaphore | None = None


# ── safe_json ─────────────────────────────────────────────────────────────────
# Copied from reclassify.py. Handles Gemma preamble, markdown fences, and
# trailing commas. Not imported to avoid module-level logging side effects.

def safe_json(text: str) -> dict:
    try:
        clean = re.sub(r"```json|```", "", text).strip()
        clean = re.sub(r",\s*([}\]])", r"\1", clean)
        return json.loads(clean)
    except Exception:
        pass
    try:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(re.sub(r",\s*([}\]])", r"\1", m.group(0)))
    except Exception:
        pass
    log.warning(f"safe_json: parse failure '{text[:120]}'")
    return {}


# ── Field registries ──────────────────────────────────────────────────────────

# Fields that go through the full LLM extraction and scoring pipeline.
EXTRACTABLE_FIELDS: list[str] = [
    "age",
    "primary_project",
    "active_projects",
    "current_business",
    "training_focus",
    "current_priorities",
    "focus_area",
]

# Fields that bypass extraction entirely. Human fills confirmed_value directly.
MANUAL_FIELDS: list[str] = [
    "active_course",
    "course_status",
    "historical_context",
]

# All fields known to this pipeline. Used for apply-mode validation.
ALL_PROFILE_FIELDS: list[str] = EXTRACTABLE_FIELDS + MANUAL_FIELDS


# ── Field config — extractable fields only ────────────────────────────────────

# Per-field strategy config. All weight sets must sum to 1.0 — enforced below.
FIELD_CONFIG: dict[str, dict] = {
    "age": {
        "ttl_days":                 365,
        "recency_half_life_days":   180,
        "recency_weight":           0.30,
        "strength_weight":          0.55,
        "corroboration_weight":     0.15,
        "retrospective_multiplier": 0.0,    # retrospective age assertions score zero
        "staleness_threshold_days": 365,
        "min_score_threshold":      0.10,
    },
    "primary_project": {
        "ttl_days":                 45,
        "recency_half_life_days":   30,
        "recency_weight":           0.50,
        "strength_weight":          0.35,
        "corroboration_weight":     0.15,
        "retrospective_multiplier": 0.30,
        "staleness_threshold_days": 90,
        "min_score_threshold":      0.10,
    },
    "active_projects": {
        "ttl_days":                 45,
        "recency_half_life_days":   30,
        "recency_weight":           0.50,
        "strength_weight":          0.35,
        "corroboration_weight":     0.15,
        "retrospective_multiplier": 0.30,
        "staleness_threshold_days": 90,
        "min_score_threshold":      0.10,
    },
    "current_business": {
        "ttl_days":                 90,
        "recency_half_life_days":   60,
        "recency_weight":           0.45,
        "strength_weight":          0.40,
        "corroboration_weight":     0.15,
        "retrospective_multiplier": 0.30,
        "staleness_threshold_days": 180,
        "min_score_threshold":      0.10,
    },
    "training_focus": {
        "ttl_days":                 30,
        "recency_half_life_days":   21,
        "recency_weight":           0.50,
        "strength_weight":          0.35,
        "corroboration_weight":     0.15,
        "retrospective_multiplier": 0.30,
        "staleness_threshold_days": 60,
        "min_score_threshold":      0.10,
    },
    "current_priorities": {
        "ttl_days":                 21,
        "recency_half_life_days":   14,
        "recency_weight":           0.55,
        "strength_weight":          0.30,
        "corroboration_weight":     0.15,
        "retrospective_multiplier": 0.20,
        "staleness_threshold_days": 45,
        "min_score_threshold":      0.10,
    },
    "focus_area": {
        "ttl_days":                 30,
        "recency_half_life_days":   21,
        "recency_weight":           0.50,
        "strength_weight":          0.35,
        "corroboration_weight":     0.15,
        "retrospective_multiplier": 0.30,
        "staleness_threshold_days": 60,
        "min_score_threshold":      0.10,
    },
}

# Enforce weight sums at import time — fail loudly rather than silently mis-score.
for _f, _c in FIELD_CONFIG.items():
    _wsum = round(_c["recency_weight"] + _c["strength_weight"] + _c["corroboration_weight"], 10)
    if abs(_wsum - 1.0) > 1e-9:
        raise ValueError(
            f"FIELD_CONFIG['{_f}']: weights sum to {_wsum}, must be exactly 1.0"
        )


# ── Manual field config ───────────────────────────────────────────────────────

# TTL-only config for manual fields. No scoring weights — no weight-sum validation.
# TTL is used by apply mode to compute stale_at.
MANUAL_FIELD_CONFIG: dict[str, dict] = {
    "active_course": {
        "ttl_days": 30,
    },
    "course_status": {
        "ttl_days": 14,
    },
    "historical_context": {
        "ttl_days": 365,
    },
}


# ── Field definitions — extractable fields only ───────────────────────────────

FIELD_QUERIES: dict[str, str] = {
    "age":               "I am years old my age",
    "primary_project":   "my main project I am building working on",
    "active_projects":   "projects I am working on currently building running",
    "current_business":  "my business company I run own operate",
    "training_focus":    "I am training studying learning focused on skill discipline",
    "current_priorities":"my priorities right now most important things to focus on",
    "focus_area":        "I am focused on my focus current priority goal",
}

FIELD_DEFINITIONS: dict[str, tuple[str, str]] = {
    "age": (
        "Alex's age",
        "A number stating how old Alex is right now. Must be a concrete integer.",
    ),
    "primary_project": (
        "Alex's primary project",
        "The main thing Alex is building or working on. A named project, business, or initiative.",
    ),
    "active_projects": (
        "Alex's active projects",
        "The projects Alex is currently working on. May be multiple — list them if so. Named projects, businesses, or initiatives.",
    ),
    "current_business": (
        "Alex's current business",
        "The business or company Alex is currently running or operating. A named entity.",
    ),
    "training_focus": (
        "Alex's training focus",
        "What Alex is currently focused on in training — a specific skill, discipline, practice, or subject.",
    ),
    "current_priorities": (
        "Alex's current priorities",
        "The things Alex considers most important right now. Goals, tasks, or areas of focus he is actively prioritising.",
    ),
    "focus_area": (
        "Alex's current focus area",
        "What Alex is primarily focused on achieving right now — a goal, direction, or phase of work.",
    ),
}

# Documentation strings written into each manual field's output entry.
# Tells the reviewer what value to provide.
MANUAL_FIELD_DESCRIPTIONS: dict[str, str] = {
    "active_course":     "The name or description of a course Alex is currently enrolled in or studying.",
    "course_status":     "Where Alex currently is in an active course — week number, module, percentage complete.",
    "historical_context":"Stable background context about Alex that rarely changes.",
}

# Updated extraction prompt: adds temporal_frame to the response schema.
# token budget: num_predict=40 — the new JSON response is marginally longer
# than the old three-key response; 40 tokens remains sufficient.
FIELD_EXTRACTION_PROMPT = """\
You are extracting a specific fact about Alex from a statement he made.

Field: {field_label}
Definition: {field_definition}

Alex's statement:
"{user_text}"

Does this statement contain a declarative assertion about {field_label}?

Reply with JSON only:
{{"found": true, "value": <value>, "confidence": "high|medium|low", "temporal_frame": "present|retrospective|prospective|unclear"}}

temporal_frame definitions:
  present       — asserts this as currently true ("I am", "I'm working on")
  retrospective — refers to a past state ("I was", "back when I was")
  prospective   — refers to an intended future state ("I'm going to", "I plan to")
  unclear       — temporal framing cannot be determined

If not found:
{{"found": false, "value": null, "confidence": null, "temporal_frame": null}}\
"""

_VALID_TEMPORAL_FRAMES = frozenset({"present", "retrospective", "prospective", "unclear"})
_VALID_CONFIDENCE      = frozenset({"high", "medium", "low"})


# ── ChromaDB ──────────────────────────────────────────────────────────────────

def get_col_facts():
    """
    Open col_facts with the embedding function required for vector search.
    Raises if the collection does not exist.
    """
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL, trust_remote_code=True
    )
    client    = chromadb.PersistentClient(path=CHROMA_PATH)
    col_facts = client.get_collection("facts", embedding_function=ef)
    return col_facts


# ── LLM extraction ────────────────────────────────────────────────────────────

async def llm_extract(field: str, user_text: str, client: httpx.AsyncClient) -> dict:
    """
    Run one field-extraction LLM call against the Ollama API.

    Returns:
        {
          "found": bool,
          "value": str | int | None,
          "confidence": "high" | "medium" | "low" | None,
          "temporal_frame": "present" | "retrospective" | "prospective" | "unclear" | None,
        }

    On any failure — connection error, empty response, JSON parse failure,
    type coercion failure — returns found=False with all nulls. Never raises.
    Out-of-enum values are normalised: temporal_frame → "unclear", confidence → "low".
    """
    assert _semaphore is not None
    label, definition = FIELD_DEFINITIONS[field]
    prompt = FIELD_EXTRACTION_PROMPT.format(
        field_label=label,
        field_definition=definition,
        user_text=user_text[:500],
    )

    _not_found = {"found": False, "value": None, "confidence": None, "temporal_frame": None}

    raw = ""
    async with _semaphore:
        for attempt in range(3):
            try:
                res = await client.post(
                    OLLAMA_CHAT_URL,
                    json={
                        "model":    MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream":   False,
                        "options":  {"temperature": 0, "num_predict": 40},
                    },
                    timeout=90,
                )
                raw = res.json()["message"]["content"].strip()
                break
            except Exception as e:
                log.warning(f"llm_extract [{field}] attempt {attempt+1}/3: {e}")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
        else:
            log.warning(f"llm_extract [{field}]: all 3 attempts failed — treating as not found")
            return _not_found

    if not raw:
        log.warning(f"llm_extract [{field}]: empty LLM response — treating as not found")
        return _not_found

    parsed = safe_json(raw)
    if not parsed:
        log.debug(f"llm_extract [{field}]: JSON parse failure — raw='{raw[:120]}'")
        return _not_found

    found = bool(parsed.get("found", False))
    value = parsed.get("value", None)

    if not found or value is None:
        return _not_found

    # Normalise confidence — out-of-enum → "low"
    confidence = parsed.get("confidence", None)
    if confidence not in _VALID_CONFIDENCE:
        log.debug(
            f"llm_extract [{field}]: confidence '{confidence}' outside enum — normalising to 'low'"
        )
        confidence = "low"

    # Normalise temporal_frame — absent or out-of-enum → "unclear"
    temporal_frame = parsed.get("temporal_frame", None)
    if temporal_frame not in _VALID_TEMPORAL_FRAMES:
        log.debug(
            f"llm_extract [{field}]: temporal_frame '{temporal_frame}' outside enum — normalising to 'unclear'"
        )
        temporal_frame = "unclear"

    # Age must be an integer. Attempt coercion if model returned a string.
    if field == "age":
        if not isinstance(value, int):
            try:
                value = int(str(value).strip())
            except (ValueError, TypeError):
                log.warning(
                    f"llm_extract [age]: value '{value}' not coercible to int — skipping"
                )
                return _not_found

    log.debug(
        f"llm_extract [{field}]: found=True value='{value}' "
        f"confidence='{confidence}' temporal_frame='{temporal_frame}'"
    )
    return {"found": True, "value": value, "confidence": confidence, "temporal_frame": temporal_frame}


# ── Scoring ───────────────────────────────────────────────────────────────────

def _normalise_value(v) -> str:
    """Normalise a candidate value for comparison (corroboration, contradiction checks)."""
    if v is None:
        return ""
    return str(v).lower().strip()


def _compute_recency_score(from_date: str | None, half_life_days: int) -> float:
    """
    Exponential decay: 1.0 at age 0, 0.5 at half_life_days, ~0.25 at 2× half_life.
    Returns 0.0 if from_date is None (unknown age — do not assume recent).
    """
    if not from_date:
        return 0.0
    try:
        dt       = datetime.strptime(from_date, "%Y-%m-%d")
        days_old = max(0, (datetime.utcnow() - dt).days)
        return math.pow(0.5, days_old / half_life_days)
    except Exception:
        return 0.0


def _compute_strength_score(confidence: str | None) -> float:
    return {"high": 1.0, "medium": 0.6, "low": 0.3}.get(confidence or "", 0.1)


def _compute_corroboration(candidate: dict, all_raw: list[dict]) -> tuple[float, int]:
    """
    Count other candidates (different source_memory_id) with the same normalised value.
    Score saturates at 3 corroborating sources → 1.0.
    Returns (score, count).
    """
    norm    = _normalise_value(candidate["value"])
    self_id = candidate.get("source_memory_id")
    count   = sum(
        1 for c in all_raw
        if _normalise_value(c["value"]) == norm
        and c.get("source_memory_id") != self_id
    )
    return min(count / 3.0, 1.0), count


def _compute_temporal_multiplier(temporal_frame: str, field_config: dict) -> float:
    return {
        "present":       1.0,
        "prospective":   0.9,
        "unclear":       0.8,
        "retrospective": field_config["retrospective_multiplier"],
    }.get(temporal_frame, 0.8)


def _score_candidate(raw: dict, all_raw: list[dict], field_config: dict) -> dict:
    """
    Score a single RawCandidate against the full raw candidate list for this field.
    Returns a ScoredCandidate dict (all raw fields plus score, score_components,
    corroboration_count).
    """
    recency_score          = _compute_recency_score(
        raw["from_date"], field_config["recency_half_life_days"]
    )
    strength_score         = _compute_strength_score(raw["confidence"])
    corr_score, corr_count = _compute_corroboration(raw, all_raw)
    temporal_mult          = _compute_temporal_multiplier(raw["temporal_frame"], field_config)

    composite = (
        field_config["recency_weight"]       * recency_score  +
        field_config["strength_weight"]      * strength_score +
        field_config["corroboration_weight"] * corr_score
    )
    final_score = composite * temporal_mult

    return {
        **raw,
        "score": final_score,
        "score_components": {
            "recency_score":       recency_score,
            "strength_score":      strength_score,
            "corroboration_score": corr_score,
            "temporal_multiplier": temporal_mult,
        },
        "corroboration_count": corr_count,
    }


def _score_and_rank(raw_candidates: list[dict], field_config: dict) -> list[dict]:
    """
    Score all raw candidates, filter below min_score_threshold, sort descending.
    Corroboration is computed against the full raw list before any filtering.
    """
    if not raw_candidates:
        return []

    scored = []
    for raw in raw_candidates:
        candidate = _score_candidate(raw, raw_candidates, field_config)
        if candidate["score"] >= field_config["min_score_threshold"]:
            scored.append(candidate)

    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored


# ── Grouping ──────────────────────────────────────────────────────────────────

def _group_candidates(scored_candidates: list[dict]) -> list[dict]:
    """
    Group scored candidates by normalised value into CandidateGroup dicts.

    Returns a list of CandidateGroup dicts sorted descending by group_score
    (= the top member's score within each group).

    Empty input returns empty list. Candidates with a None/empty normalised
    value are grouped under "" — this should not occur if _score_and_rank did
    its job, but the grouper must not raise.
    """
    if not scored_candidates:
        return []

    # Build group buckets keyed by normalised value
    buckets: dict[str, list[dict]] = {}
    for candidate in scored_candidates:
        key = _normalise_value(candidate["value"])
        if key not in buckets:
            buckets[key] = []
        buckets[key].append(candidate)

    groups: list[dict] = []
    for key, members in buckets.items():
        # Sort members by score descending within the group
        members.sort(key=lambda m: m["score"], reverse=True)
        top_member = members[0]

        # Collect unique evidence snippets up to MAX_EVIDENCE_PER_GROUP
        seen_evidence: set[str] = set()
        evidence_snippets: list[str] = []
        for m in members:
            ev = m.get("evidence", "").strip()
            if ev and ev not in seen_evidence:
                seen_evidence.add(ev)
                evidence_snippets.append(ev)
            if len(evidence_snippets) >= MAX_EVIDENCE_PER_GROUP:
                break

        # Collect all distinct source_memory_ids across the group (order-preserving)
        source_ids = [m["source_memory_id"] for m in members if m.get("source_memory_id")]
        unique_source_ids = list(dict.fromkeys(source_ids))

        groups.append({
            "normalised_key":    key,
            "display_value":     top_member["value"],
            "group_score":       top_member["score"],
            "member_count":      len(members),
            "source_memory_ids": unique_source_ids,
            "evidence_snippets": evidence_snippets,
            "top_member":        top_member,
        })

    # Sort groups by group_score descending
    groups.sort(key=lambda g: g["group_score"], reverse=True)
    return groups


# ── Flag generation ───────────────────────────────────────────────────────────

def _generate_flags_from_groups(
    groups: list[dict],
    field_config: dict,
) -> tuple[list[str], dict | None, list[dict]]:
    """
    Evaluate the ranked group list and produce diagnostic flags.

    Returns:
        (flags, top_group, alternative_groups)
        top_group is None if groups is empty.
    """
    if not groups:
        return ["no_candidates"], None, []

    top_group         = groups[0]
    alternative_groups = groups[1:]
    flags: list[str] = []

    # Contradiction: top and second group have different normalised values
    # and their group_scores are close.
    if alternative_groups:
        second_group = alternative_groups[0]
        score_gap    = top_group["group_score"] - second_group["group_score"]
        if top_group["normalised_key"] != second_group["normalised_key"]:
            if score_gap < CONTRADICTION_SCORE_GAP_THRESHOLD:
                flags.append("contradiction")
                log.info(
                    f"contradiction flag: "
                    f"top='{top_group['display_value']}' score={top_group['group_score']:.4f} "
                    f"vs second='{second_group['display_value']}' score={second_group['group_score']:.4f} "
                    f"gap={score_gap:.4f} threshold={CONTRADICTION_SCORE_GAP_THRESHOLD}"
                )

    # Stale top: top group's top_member from_date exceeds staleness threshold.
    top_member = top_group["top_member"]
    if top_member.get("from_date"):
        try:
            dt       = datetime.strptime(top_member["from_date"], "%Y-%m-%d")
            days_old = (datetime.utcnow() - dt).days
            if days_old > field_config["staleness_threshold_days"]:
                flags.append("stale_top")
                log.info(
                    f"stale_top flag: top group top_member is {days_old} days old "
                    f"(threshold={field_config['staleness_threshold_days']})"
                )
        except Exception:
            pass

    # Retrospective-only: check top_member of every group.
    # A group is considered retrospective if its best member is — sufficient
    # for the flag; full member traversal is not required.
    all_frames = [g["top_member"]["temporal_frame"] for g in groups]
    if all(f == "retrospective" for f in all_frames):
        flags.append("retrospective_only")
        log.warning(
            f"retrospective_only flag: all {len(groups)} groups have retrospective top_member. "
            f"top score={top_group['group_score']:.4f} — check multiplier config if unexpected."
        )

    return flags, top_group, alternative_groups


# ── Result constructors ───────────────────────────────────────────────────────

def _empty_group_result() -> dict:
    """Blank RankedGroupResult for extractable fields where ChromaDB returned nothing."""
    return {
        "field_type":          "extractable",
        "top_group":           None,
        "alternative_groups":  [],
        "flags":               ["no_candidates"],
        "action":              None,
        "confirmed_value":     None,
        "confirmed_alt_index": None,
    }


def _manual_field_result(field_name: str) -> dict:
    """ManualFieldResult for a named manual field. No extraction is attempted."""
    return {
        "field_type":          "manual",
        "description":         MANUAL_FIELD_DESCRIPTIONS[field_name],
        "top_group":           None,
        "alternative_groups":  [],
        "flags":               ["manual_entry_required"],
        "action":              None,
        "confirmed_value":     None,
        "confirmed_alt_index": None,
    }


# ── Apply resolution ──────────────────────────────────────────────────────────

def _resolve_confirmed_value(
    fname: str,
    ranked: dict,
) -> tuple[object, dict | None, str | None, int | None]:
    """
    Interpret the human-set action on a V3 field entry and return what to write.

    Returns:
        (write_value, source_candidate, action_taken, candidate_rank)

    write_value=None means skip this field entirely.
    candidate_rank: 1=top_group, 2+=alternative_groups (1-based). None if no source.

    Dispatch is on field_type. Manual fields only accept "edit" or "skip".
    Extractable fields accept all four actions.
    """
    field_type = ranked.get("field_type", "extractable")
    action     = ranked.get("action")

    if not action or action == "skip":
        return None, None, None, None

    # ── Manual field dispatch ─────────────────────────────────────────────────
    if field_type == "manual":
        if action not in ("edit", "skip"):
            log.warning(
                f"apply [{fname}]: action='{action}' is invalid for a manual field "
                f"(only 'edit' or 'skip' are valid) — skipping"
            )
            return None, None, None, None
        confirmed_value = ranked.get("confirmed_value")
        if confirmed_value is None:
            log.warning(
                f"apply [{fname}]: action=edit on manual field but confirmed_value is null — skipping"
            )
            return None, None, None, None
        # source_candidate is None for manual fields — no provenance to cite
        return confirmed_value, None, "edit_manual", None

    # ── Extractable field dispatch ────────────────────────────────────────────
    top_group          = ranked.get("top_group")
    alternative_groups = ranked.get("alternative_groups") or []

    if action == "accept_top":
        if top_group is None:
            log.warning(f"apply [{fname}]: action=accept_top but top_group is null — skipping")
            return None, None, None, None
        return top_group["display_value"], top_group["top_member"], "accept_top", 1

    if action == "accept_other":
        idx = ranked.get("confirmed_alt_index")
        if idx is None or not isinstance(idx, int) or idx < 0 or idx >= len(alternative_groups):
            log.warning(
                f"apply [{fname}]: invalid confirmed_alt_index={idx} "
                f"(alternative_groups has {len(alternative_groups)} entries) — skipping"
            )
            return None, None, None, None
        grp = alternative_groups[idx]
        return grp["display_value"], grp["top_member"], "accept_other", idx + 2

    if action == "edit":
        confirmed_value = ranked.get("confirmed_value")
        if confirmed_value is None:
            log.warning(f"apply [{fname}]: action=edit but confirmed_value is null — skipping")
            return None, None, None, None
        if fname == "age":
            try:
                confirmed_value = int(str(confirmed_value).strip())
            except (ValueError, TypeError):
                log.warning(
                    f"apply [age]: confirmed_value '{confirmed_value}' not coercible to int — skipping"
                )
                return None, None, None, None
        source = top_group["top_member"] if top_group else None
        rank   = 1 if top_group else None
        return confirmed_value, source, "edit", rank

    log.warning(f"apply [{fname}]: unrecognised action='{action}' — skipping")
    return None, None, None, None


# ── TTL lookup (works for both FIELD_CONFIG and MANUAL_FIELD_CONFIG) ──────────

def _get_ttl_days(fname: str) -> int:
    """
    Return the ttl_days for fname, consulting FIELD_CONFIG first then
    MANUAL_FIELD_CONFIG. Falls back to 30 for unknown fields with a warning.
    """
    if fname in FIELD_CONFIG:
        return FIELD_CONFIG[fname]["ttl_days"]
    if fname in MANUAL_FIELD_CONFIG:
        return MANUAL_FIELD_CONFIG[fname]["ttl_days"]
    log.warning(f"_get_ttl_days: unknown field '{fname}' — defaulting to 30 days")
    return 30


# ── Extract mode ──────────────────────────────────────────────────────────────

async def extract_mode(output_path: Path, candidates_per_field: int) -> None:
    global _semaphore
    _semaphore = asyncio.Semaphore(CONCURRENCY)

    print(f"\n{'─'*60}")
    print(f"Lucchese Profile Seeding V3 — EXTRACT mode")
    print(f"Model             : {MODEL}")
    print(f"Chroma path       : {CHROMA_PATH}")
    print(f"Candidates/field  : {candidates_per_field}")
    print(f"Output            : {output_path}")
    print(f"Log               : {_log_path}")
    print(f"{'─'*60}\n")

    # ── Check Ollama before touching ChromaDB ─────────────────────────────────
    async with httpx.AsyncClient() as _probe:
        try:
            await _probe.get(OLLAMA_BASE_URL, timeout=5)
            print("✓ Ollama reachable")
        except Exception:
            print(f"✗ Ollama unreachable at {OLLAMA_BASE_URL}")
            print("  Run `ollama serve` and try again.")
            sys.exit(1)

    # ── Open col_facts ────────────────────────────────────────────────────────
    print("  Opening col_facts...")
    try:
        col_facts = get_col_facts()
    except Exception as e:
        print(f"✗ Cannot open col_facts: {e}")
        print("  Run reclassify.py first to create and populate col_facts.")
        sys.exit(1)

    total_facts = col_facts.count()
    if total_facts == 0:
        print("✗ col_facts is empty — run reclassify.py first")
        sys.exit(1)
    print(f"✓ col_facts: {total_facts} entries")

    # ── Probe for personal/self entries ───────────────────────────────────────
    try:
        probe = col_facts.get(
            where={
                "$and": [
                    {"source_type": {"$eq": "self"}},
                    {"is_personal": {"$eq": "true"}},
                ]
            },
            limit=1,
            include=["metadatas"],
        )
        if not probe["ids"]:
            print("✗ No entries with source_type=self found in col_facts")
            print(
                "  reclassify.py has not been run, or produced no self-sourced entries."
            )
            sys.exit(1)
        print("✓ Personal/self entries present\n")
    except Exception as e:
        print(f"✗ Probe query failed: {e}")
        sys.exit(1)

    # ── Source summary (best-effort) ──────────────────────────────────────────
    personal_self_count = -1
    chatgpt_grok_count  = -1
    try:
        all_personal = col_facts.get(
            where={
                "$and": [
                    {"source_type": {"$eq": "self"}},
                    {"is_personal": {"$eq": "true"}},
                ]
            },
            include=["metadatas"],
        )
        personal_self_count = len(all_personal["ids"])
        chatgpt_grok_count  = sum(
            1 for m in all_personal["metadatas"]
            if m.get("source") in ("chatgpt", "grok")
        )
    except Exception as e:
        log.warning(f"Source summary query failed (non-fatal): {e}")

    # ── ChromaDB filter applied to all field queries ───────────────────────────
    extraction_filter = {
        "$and": [
            {"source_type": {"$eq": "self"}},
            {"is_personal": {"$eq": "true"}},
            {"source":      {"$in": ["chatgpt", "grok"]}},
        ]
    }

    fields_output: dict[str, dict] = {}

    # ── Phase 1: Extractable fields ───────────────────────────────────────────
    async with httpx.AsyncClient() as client:
        for field in EXTRACTABLE_FIELDS:
            config = FIELD_CONFIG[field]
            print(f"  [{field}]")
            log.info(f"EXTRACT field={field} candidates_per_field={candidates_per_field}")

            # ChromaDB query — ids always returned alongside metadatas
            try:
                results   = col_facts.query(
                    query_texts=[FIELD_QUERIES[field]],
                    n_results=candidates_per_field,
                    where=extraction_filter,
                    include=["metadatas"],
                )
                metadatas: list[dict] = results["metadatas"][0] if results.get("metadatas") else []
                doc_ids:   list[str]  = results["ids"][0]       if results.get("ids")       else []
            except Exception as e:
                log.warning(f"ChromaDB query failed for field '{field}': {e}")
                print(f"    ✗ Query error: {e}")
                fields_output[field] = _empty_group_result()
                continue

            if not metadatas:
                log.info(f"[{field}]: 0 candidates returned")
                print(f"    – 0 candidates")
                fields_output[field] = _empty_group_result()
                continue

            # Sort paired (meta, doc_id) by created_at descending — most recent first.
            # Null/missing created_at values sort to the end.
            paired_sorted = sorted(
                zip(metadatas, doc_ids),
                key=lambda pair: pair[0].get("created_at") or "",
                reverse=True,
            )

            raw_candidates: list[dict] = []

            for meta, doc_id in paired_sorted:
                user_text = meta.get("user_text_raw", "").strip()
                if not user_text:
                    log.debug(f"[{field}] doc_id={doc_id}: empty user_text_raw — skip")
                    continue

                extraction = await llm_extract(field, user_text, client)

                if extraction["found"] and extraction["value"] is not None:
                    created_at = meta.get("created_at", "")
                    from_date  = created_at[:10] if created_at else None
                    raw_candidates.append({
                        "value":            extraction["value"],
                        "confidence":       extraction["confidence"],
                        "temporal_frame":   extraction["temporal_frame"] or "unclear",
                        "from_date":        from_date,
                        "from_source":      meta.get("source"),
                        "evidence":         user_text[:300],
                        "source_memory_id": doc_id,
                    })
                    log.info(
                        f"RAW_FOUND [{field}]: value='{extraction['value']}' "
                        f"confidence='{extraction['confidence']}' "
                        f"temporal_frame='{extraction['temporal_frame']}' "
                        f"source='{meta.get('source')}' "
                        f"date='{from_date}'"
                    )
                # No break — exhaustive extraction continues through all candidates

            log.info(
                f"[{field}]: exhaustive pass complete — "
                f"{len(raw_candidates)} assertions found from {len(paired_sorted)} candidates checked"
            )
            print(
                f"    → {len(raw_candidates)} assertions found from {len(paired_sorted)} candidates"
            )

            # Score and rank
            scored = _score_and_rank(raw_candidates, config)
            log.info(
                f"[{field}]: {len(scored)} candidates above "
                f"min_score_threshold={config['min_score_threshold']} after scoring"
            )

            # Group by normalised value
            groups = _group_candidates(scored)
            log.info(f"[{field}]: {len(groups)} distinct value group(s) after grouping")

            # Flags
            flags, top_group, alternative_groups = _generate_flags_from_groups(groups, config)

            if flags:
                print(f"    ⚑ flags: {', '.join(flags)}")

            if top_group is not None:
                print(
                    f"    ✓ top: {top_group['display_value']} "
                    f"(score={top_group['group_score']:.3f}, "
                    f"{top_group['member_count']} source(s), "
                    f"{top_group['top_member']['temporal_frame']})"
                )
                if alternative_groups:
                    print(f"    + {len(alternative_groups)} alternative group(s)")
            else:
                print(f"    – No candidates above threshold")

            if top_group is None:
                fields_output[field] = _empty_group_result()
            else:
                fields_output[field] = {
                    "field_type":          "extractable",
                    "top_group":           top_group,
                    "alternative_groups":  alternative_groups,
                    "flags":               flags,
                    "action":              None,
                    "confirmed_value":     None,
                    "confirmed_alt_index": None,
                }

    # ── Phase 2: Manual fields ────────────────────────────────────────────────
    print()
    for field in MANUAL_FIELDS:
        print(f"  [{field}]")
        print(f"    – manual entry required (set confirmed_value in output file and run --apply)")
        fields_output[field] = _manual_field_result(field)

    # ── Write output file ─────────────────────────────────────────────────────
    extractable_with_top = sum(
        1 for f in EXTRACTABLE_FIELDS
        if fields_output.get(f, {}).get("top_group") is not None
    )

    output_data = {
        "schema_version": SCHEMA_VERSION,
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "source_summary": {
            "total_facts_scanned":    total_facts,
            "personal_self_filtered": personal_self_count,
            "chatgpt_grok_only":      chatgpt_grok_count,
        },
        "fields": fields_output,
    }

    try:
        output_path.write_text(
            json.dumps(output_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:
        log.error(f"Failed to write output file: {e}")
        print(f"\n✗ Could not write {output_path}: {e}")
        sys.exit(1)

    print(f"\n{'─'*60}")
    print(f"✓ Extraction complete (V3 — grouped and ranked)")
    print(f"  Extractable fields with top group : {extractable_with_top}/{len(EXTRACTABLE_FIELDS)}")
    print(f"  Manual fields (human input required): {len(MANUAL_FIELDS)}")
    print(f"  Output                             : {output_path}")
    print(f"\nNext steps:")
    print(f"  1. Open {output_path}")
    print(f"  2. For each extractable field, review top_group and alternative_groups.")
    print(f"     Set \"action\" to one of:")
    print(f"       \"accept_top\"   — use the top-ranked group's display_value")
    print(f"       \"accept_other\" — set confirmed_alt_index (0-based into alternative_groups)")
    print(f"       \"edit\"         — set confirmed_value to your corrected value")
    print(f"       \"skip\"         — do not write this field")
    print(f"  3. For each manual field, set action=\"edit\" and fill in confirmed_value.")
    print(f"  4. Run: python seed_profile.py --apply --input {output_path}")
    print(f"\n  Log: {_log_path}")
    print(f"{'─'*60}\n")


# ── Apply mode ────────────────────────────────────────────────────────────────

def apply_mode(input_path: Path, api_base: str) -> None:
    print(f"\n{'─'*60}")
    print(f"Lucchese Profile Seeding V3 — APPLY mode")
    print(f"Input    : {input_path}")
    print(f"API base : {api_base}")
    print(f"{'─'*60}\n")

    # ── Read and validate ──────────────────────────────────────────────────────
    if not input_path.exists():
        print(f"✗ File not found: {input_path}")
        print(f"  Run --extract first to generate the candidate file.")
        sys.exit(1)

    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"✗ JSON parse error in {input_path}:")
        print(f"  {e}")
        sys.exit(1)

    if "fields" not in data:
        print(f"✗ Invalid candidate file: missing 'fields' key")
        sys.exit(1)

    fields_data: dict = data["fields"]

    # ── Schema detection ──────────────────────────────────────────────────────
    # V2 schema: each field entry has "top_candidate" key (no field_type).
    # V3 schema: each field entry has "field_type" key (no top_candidate).
    # Unknown/malformed: neither key present.
    # Check the first valid dict entry — that's sufficient to determine schema.
    for fname, entry in fields_data.items():
        if isinstance(entry, dict):
            if "top_candidate" in entry:
                print(f"V2 schema detected in {input_path}.")
                print(f"  This file was produced by seed_profile.py V2 and is incompatible with V3.")
                try:
                    input_path.unlink()
                    print(f"  File deleted.")
                except Exception as del_err:
                    print(f"  Could not delete file: {del_err}")
                print(f"  Re-run: python seed_profile.py --extract")
                sys.exit(1)
            if "field_type" not in entry:
                print(f"Unrecognised schema in {input_path} (missing 'field_type' key).")
                try:
                    input_path.unlink()
                    print(f"  File deleted.")
                except Exception as del_err:
                    print(f"  Could not delete file: {del_err}")
                print(f"  Re-run: python seed_profile.py --extract")
                sys.exit(1)
            break  # schema version determined from first valid entry

    # ── Resolve and validate each field ──────────────────────────────────────
    now_dt  = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    patch_payload:      dict  = {}
    field_meta_payload: dict  = {}
    written_fields:     list  = []  # [(fname, write_value, stale_at_iso)]
    skipped_fields:     list  = []

    for fname, ranked in fields_data.items():
        if fname not in ALL_PROFILE_FIELDS:
            log.warning(f"apply: unknown field '{fname}' in candidate file — skipping")
            continue

        write_value, source_candidate, action_taken, candidate_rank = _resolve_confirmed_value(
            fname, ranked
        )

        if write_value is None:
            skipped_fields.append(fname)
            log.info(f"apply [{fname}]: skipped (action={ranked.get('action')!r})")
            continue

        # ── Build AuditRecord ─────────────────────────────────────────────────
        ttl_days     = _get_ttl_days(fname)
        stale_at_dt  = now_dt + timedelta(days=ttl_days)
        stale_at_iso = stale_at_dt.isoformat()

        audit: dict = {
            "confirmed_at":          now_iso,
            "action_taken":          action_taken,
            "confirmed_value":       write_value,
            "candidate_score":       source_candidate["score"]            if source_candidate else None,
            "candidate_rank":        candidate_rank,
            "seeded_from_date":      source_candidate["from_date"]        if source_candidate else None,
            "seeded_from_source":    source_candidate["from_source"]      if source_candidate else None,
            "source_memory_id":      source_candidate["source_memory_id"] if source_candidate else None,
            "confidence":            source_candidate["confidence"]       if source_candidate else None,
            "flags_at_confirmation": ranked.get("flags", []),
            "stale_at":              stale_at_iso,
        }

        patch_payload[fname]      = write_value
        field_meta_payload[fname] = audit
        written_fields.append((fname, write_value, stale_at_iso))

        score_str = f"{source_candidate['score']:.4f}" if source_candidate else "N/A"
        log.info(
            f"apply [{fname}]: value='{write_value}' action={action_taken} "
            f"score={score_str} rank={candidate_rank} stale_at={stale_at_iso}"
        )

    if not written_fields:
        print("No fields to write.")
        if skipped_fields:
            print(f"  Skipped: {', '.join(skipped_fields)}")
        print(
            f"  Open {input_path}, set action on the fields you want to apply, "
            f"then re-run --apply."
        )
        sys.exit(0)

    patch_payload["confirmed"]  = True
    patch_payload["field_meta"] = field_meta_payload

    print(f"Fields to write ({len(written_fields)}):")
    for fname, value, _ in written_fields:
        print(f"  {fname}: {value}")
    if skipped_fields:
        print(f"\nSkipped ({len(skipped_fields)}): {', '.join(skipped_fields)}")
    print()

    # ── PATCH /state/profile ──────────────────────────────────────────────────
    url = f"{api_base.rstrip('/')}/state/profile"

    try:
        with httpx.Client(timeout=30) as http_client:
            resp = http_client.patch(url, json=patch_payload)
    except httpx.ConnectError:
        print(f"✗ Cannot connect to API at {url}")
        print("  Is the server running? Check LUCCHESE_API_BASE or --api-base.")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Request failed: {e}")
        sys.exit(1)

    if resp.status_code != 200:
        print(f"✗ API returned HTTP {resp.status_code}:")
        print(f"  {resp.text}")
        sys.exit(1)

    print("✓ Profile updated successfully")
    print(f"\nWritten fields:")
    for fname, value, stale_at_iso in written_fields:
        print(f"  {fname}: {value}")

    # Log TTL / potential stale entries per user instruction.
    # These are informational — enforcement is context_builder.py's responsibility.
    print()
    for fname, value, stale_at_iso in written_fields:
        log.warning(
            f"POTENTIAL_STALE_ENTRY [{fname}]: value='{value}' "
            f"ttl_days={_get_ttl_days(fname)} "
            f"stale_at={stale_at_iso}"
        )

    print(f"  Keep {input_path} — it is your audit trail.")
    print(f"  Log: {_log_path}")
    print(f"{'─'*60}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lucchese Profile Seeding Pipeline V3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--extract", action="store_true",
        help="Scan col_facts exhaustively and write scored profile_candidates.json",
    )
    mode_group.add_argument(
        "--apply", action="store_true",
        help="Apply reviewed candidates from candidate file to profile_state via API",
    )

    parser.add_argument(
        "--output", type=Path, default=Path("profile_candidates.json"),
        metavar="PATH",
        help="Output path for candidate file (extract mode, default: profile_candidates.json)",
    )
    parser.add_argument(
        "--input", type=Path, default=Path("profile_candidates.json"),
        metavar="PATH",
        help="Input candidate file (apply mode, default: profile_candidates.json)",
    )
    parser.add_argument(
        "--candidates-per-field", type=int, default=10, dest="candidates_per_field",
        metavar="N",
        help="Max candidates to query per field in extract mode (default: 10)",
    )
    parser.add_argument(
        "--api-base", type=str, default=API_BASE, dest="api_base",
        metavar="URL",
        help=f"FastAPI base URL for apply mode (default: {API_BASE})",
    )

    args = parser.parse_args()

    if args.extract:
        asyncio.run(extract_mode(args.output, args.candidates_per_field))
    else:
        apply_mode(args.input, args.api_base)


if __name__ == "__main__":
    main()
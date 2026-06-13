"""
config/memory_settings.py
Tunable VALUES for the memory subsystem (Rule 16). The processing, ingestion, and
retrieval code in memory/ reads these constants.
"""

from __future__ import annotations

# ── Embedding ─────────────────────────────────────────────────────────────────
EMBED_MODEL: str = "nomic-ai/nomic-embed-text-v1"
RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# ── Chunking ──────────────────────────────────────────────────────────────────
CHUNK_SIZE: int = 800
CHUNK_OVERLAP: int = 100

# ── Deduplication / scoring ───────────────────────────────────────────────────
# L2 distance — lower is stricter dedup.
SIMILARITY_THRESHOLD: float = 0.25
# Distance below which "forget" considers a match close enough to delete.
FORGET_MATCH_THRESHOLD: float = 0.3
# Recency bonus weight applied to cross-encoder scores during reranking.
RECENCY_WEIGHT: float = 0.1

# ── Ingestion thresholds ──────────────────────────────────────────────────────
FACT_MIN_CHARS: int = 50
STYLE_MIN_CHARS: int = 100

# ── Classification categories ─────────────────────────────────────────────────
CATEGORIES: list[str] = [
    "ptpreps", "coaching", "fitness", "food", "cooking", "health",
    "compounds", "supplements_nootropics", "psychedelics", "property",
    "finance", "money", "lucchese", "tech", "security", "ai", "hardware",
    "content", "music", "media_gaming", "psychology", "mindset",
    "neuroscience", "social_dynamics", "family", "relationships", "travel",
    "spirituality", "conspiracy", "religion_esoteric", "philosophy",
    "politics", "economics", "history_culture", "science", "mental_health",
    "career", "pub", "general",
]

CATEGORY_LIST: str = ", ".join(CATEGORIES)

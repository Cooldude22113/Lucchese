"""
memory/processing/summarisation.py
Collapse memory clusters into dense per-category summaries (Rule 7).

Groups all facts + knowledge by category and uses the local model to write one
summary per category (skipping thin categories), upserting each via the summary
ingestor. Used by the admin "summarise" flow and the RAG system prompt.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from config.model_settings import MODEL_FAST, SUMMARISE_TIMEOUT
from memory.collections.collection_registry import get_facts, get_knowledge
from memory.ingestion.summary_ingestor import upsert_summary
from model_runtime.providers import ollama_provider

MIN_ENTRIES = 5  # categories with fewer entries are skipped (not enough signal)


def _build_summary_prompt(category: str, combined: str) -> str:
    return f"""You are summarising Alex Hammond's memory about the topic: "{category}".

The following are real things Alex has said or discussed in past conversations.
Write a dense, coherent summary of everything you know about Alex in relation to this topic.
Include specific details, preferences, history, goals, and any recurring themes.
Write it as a factual third-person profile, like a knowledgeable assistant briefing someone about Alex.
Do not include generic filler — only specific, useful information.
Keep it under 400 words.

--- Memory entries ---
{combined}
---

Summary:"""


async def summarise_all() -> dict:
    """
    Summarise every category with >= MIN_ENTRIES entries. Returns a per-category
    results log. Never raises for a single category — errors are recorded.
    """
    now = datetime.now(timezone.utc).isoformat()
    results_log: dict = {}

    # Collect docs from facts + knowledge.
    all_docs: list[dict] = []
    for col, label in [(get_facts(), "facts"), (get_knowledge(), "knowledge")]:
        try:
            results = col.get(include=["documents", "metadatas"])
            for doc, meta in zip(results["documents"], results["metadatas"]):
                if doc.strip():
                    all_docs.append({
                        "text": doc.strip(),
                        "category": meta.get("category", "general"),
                    })
        except Exception as e:
            print(f"Summarise collect error ({label}): {e}")
            results_log[label] = f"error: {e}"

    # Group by category.
    by_category: dict[str, list[str]] = defaultdict(list)
    for d in all_docs:
        by_category[d["category"]].append(d["text"])

    # Summarise each category.
    for category, texts in by_category.items():
        if len(texts) < MIN_ENTRIES:
            results_log[category] = f"skipped ({len(texts)} entries, need {MIN_ENTRIES})"
            continue

        sample = texts[:15]  # cap to avoid huge prompts
        combined = "\n\n---\n\n".join(sample)

        try:
            summary_text = (await ollama_provider.complete(
                [{"role": "user", "content": _build_summary_prompt(category, combined)}],
                model=MODEL_FAST,
                timeout=SUMMARISE_TIMEOUT,
            )).strip()

            upsert_summary(category, summary_text, len(texts), now)
            results_log[category] = f"ok ({len(texts)} entries summarised)"
            print(f"Summarised: {category} ({len(texts)} entries)")
        except Exception as e:
            print(f"Summarise error ({category}): {e}")
            results_log[category] = f"error: {e}"

    return results_log

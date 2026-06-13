"""
memory/processing/classification.py
Single-category classification of a memory chunk (Rule 7).

Always uses the local Ollama model directly (fast, private, no API cost) regardless
of CHAT_PROVIDER. Falls back to "general" on any failure.
"""

from __future__ import annotations

from config.memory_settings import CATEGORIES, CATEGORY_LIST
from config.model_settings import CLASSIFY_TIMEOUT, MODEL_FAST
from model_runtime.providers import ollama_provider


async def classify_memory(text: str) -> str:
    """Classify text into exactly one category from CATEGORIES, or 'general'."""
    prompt = (
        "Classify this text into exactly one category. Reply with only the category "
        "name, nothing else, no punctuation, no explanation.\n\n"
        f"Categories: {CATEGORY_LIST}\n\n"
        f"Text: {text[:500]}\n\n"
        "Category:"
    )
    try:
        content = await ollama_provider.complete(
            [{"role": "user", "content": prompt}],
            model=MODEL_FAST,
            options={"temperature": 0, "num_predict": 10},
            timeout=CLASSIFY_TIMEOUT,
        )
        result = content.strip().lower()
        result = result.split()[0].strip(".,\n")
        return result if result in CATEGORIES else "general"
    except Exception as e:
        print(f"classify_memory error: {e}")
        return "general"

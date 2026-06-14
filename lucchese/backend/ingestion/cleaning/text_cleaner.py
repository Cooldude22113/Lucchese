"""
ingestion/cleaning/text_cleaner.py
Orchestrates the cleaning passes over imported display text (Rule 8).

The conversation pipeline calls clean_text() on each message's display text before
persisting. Order: strip structural noise → normalise unicode/mojibake → collapse
adjacent duplicate lines → (no-op) PII pass. The raw_text kept on each message
preserves the un-cleaned original for fidelity.
"""

from __future__ import annotations

from ingestion.cleaning.duplicate_cleaner import collapse_duplicates
from ingestion.cleaning.noise_filter import strip_noise
from ingestion.cleaning.normaliser import normalise
from ingestion.cleaning.pii_filter import filter_pii


def clean_text(text: str | None) -> str | None:
    """Run the full cleaning chain; returns None/empty unchanged."""
    if not text:
        return text
    text = strip_noise(text)
    text = normalise(text)
    text = collapse_duplicates(text)
    text = filter_pii(text)
    return text.strip() if text else text

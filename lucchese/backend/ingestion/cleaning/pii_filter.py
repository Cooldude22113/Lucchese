"""
ingestion/cleaning/pii_filter.py
Conservative PII handling for imported text (Rule 8).

This is Alex's own private data, so the policy is deliberately minimal: we do NOT
redact by default (it would destroy fidelity of his own conversations). The filter
is a no-op pass-through that exists as the seam where a redaction policy would live
if these conversations were ever shared externally.
"""

from __future__ import annotations


def filter_pii(text: str | None, redact: bool = False) -> str | None:
    """
    Return text unchanged by default (Alex's own data, full fidelity kept).

    `redact=True` is reserved for a future export/sharing path; no redaction rules
    are applied today.
    """
    return text

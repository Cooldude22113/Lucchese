"""
context/context_result.py
The ContextResult value object (Rule 6).

Internal context object produced by build_context() and passed into the system
prompt builder. Not persisted, not exposed via API. Tier status fields exist for
context-assembly observability (see context/context_logging.py).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ContextResult:
    """
    Tier status values: "populated" | "empty_source" | "failure" | "unknown".
      populated    — retrieval succeeded and returned non-empty content
      empty_source — retrieval succeeded but the source had nothing
      failure      — retrieval raised (the *_error_type carries the class name)
      unknown      — field was never set (signals a missed construction site)

    tier2_result_count is a proxy: search_memory() returns a pre-formatted string,
    so 1 = non-empty, 0 = empty.
    """
    tier1_block: str = ""
    tier2_block: str = ""
    has_profile: bool = False

    tier1_status: str = "unknown"
    tier1_error_type: str = ""
    tier1_char_count: int = 0

    tier2_status: str = "unknown"
    tier2_error_type: str = ""
    tier2_char_count: int = 0
    tier2_result_count: int = 0


# Callers needing an empty context (scrape, action plan, etc.) can reuse this.
EMPTY_CONTEXT = ContextResult()

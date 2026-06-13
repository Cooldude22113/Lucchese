"""
context/context_logging.py
Structured observability for context assembly (Rule 6 + Rule 15).

Emits one INFO JSON entry per inference capturing tier statuses, char counts, and
context sources at the point the system prompt is built, plus conditional WARNING
entries on tier failure or a null context. Never raises — a logging error must
never affect inference availability.

The "lucchese.context" logger's handlers/rotation are configured at startup in
observability/logging_config.py.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from context.context_result import ContextResult

_context_logger = logging.getLogger("lucchese.context")


def emit_context_log(
    context_result: "ContextResult | None",
    inference_path: str,  # "chat" or "voice"
    web_context: str,
    sheets_context: str,
) -> None:
    """Emit the context_assembly log entry (+ conditional warnings). Never raises."""
    try:
        _now = datetime.now(timezone.utc)
        ts = _now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{_now.microsecond // 1000:03d}Z"

        web = web_context or ""
        sheet = sheets_context or ""

        if context_result is None:
            try:
                _context_logger.warning(json.dumps({
                    "event": "context_assembly_null",
                    "timestamp": ts,
                    "inference_path": inference_path,
                    "impact": "model_will_proceed_with_no_assembled_context",
                }))
            except Exception:
                pass

            _context_logger.info(json.dumps({
                "event": "context_assembly",
                "timestamp": ts,
                "inference_path": inference_path,
                "tier1_status": "unknown",
                "tier1_error_type": "",
                "tier1_char_count": 0,
                "tier2_status": "unknown",
                "tier2_error_type": "",
                "tier2_char_count": 0,
                "tier2_result_count": 0,
                "web_context_present": len(web) > 0,
                "web_context_char_count": len(web),
                "sheets_context_present": len(sheet) > 0,
                "sheets_context_char_count": len(sheet),
                "total_assembled_char_count": len(web) + len(sheet),
                "context_result_present": False,
            }))
            return

        for tier_label, status, error_type in (
            ("tier1", context_result.tier1_status, context_result.tier1_error_type),
            ("tier2", context_result.tier2_status, context_result.tier2_error_type),
        ):
            if status == "failure":
                try:
                    _context_logger.warning(json.dumps({
                        "event": "context_tier_failure",
                        "timestamp": ts,
                        "inference_path": inference_path,
                        "tier": tier_label,
                        "error_type": error_type,
                        "impact": "model_will_proceed_without_tier",
                    }))
                except Exception:
                    pass

        total = (
            context_result.tier1_char_count
            + context_result.tier2_char_count
            + len(web)
            + len(sheet)
        )
        _context_logger.info(json.dumps({
            "event": "context_assembly",
            "timestamp": ts,
            "inference_path": inference_path,
            "tier1_status": context_result.tier1_status,
            "tier1_error_type": context_result.tier1_error_type,
            "tier1_char_count": context_result.tier1_char_count,
            "tier2_status": context_result.tier2_status,
            "tier2_error_type": context_result.tier2_error_type,
            "tier2_char_count": context_result.tier2_char_count,
            "tier2_result_count": context_result.tier2_result_count,
            "web_context_present": len(web) > 0,
            "web_context_char_count": len(web),
            "sheets_context_present": len(sheet) > 0,
            "sheets_context_char_count": len(sheet),
            "total_assembled_char_count": total,
            "context_result_present": True,
        }))

    except Exception:
        # Logging must never surface to the caller.
        pass

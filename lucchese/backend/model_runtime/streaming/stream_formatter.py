"""
model_runtime/streaming/stream_formatter.py
NDJSON envelope builders for the chat/voice streaming protocol.

The frontend consumes an application/x-ndjson stream of three line types:
  {"type": "meta",  "conversation_id": ..., "web_search_used": ...}
  {"type": "token", "content": ...}
  {"type": "done",  "auto_ingested": ...}

These builders centralise the wire format so routes/flows never hand-assemble it.
"""

from __future__ import annotations

import json


def meta_line(conversation_id: str, web_search_used: bool = False) -> str:
    return json.dumps({
        "type": "meta",
        "conversation_id": conversation_id,
        "web_search_used": web_search_used,
    }) + "\n"


def token_line(content: str) -> str:
    return json.dumps({"type": "token", "content": content}) + "\n"


def done_line(auto_ingested: bool = False) -> str:
    return json.dumps({"type": "done", "auto_ingested": auto_ingested}) + "\n"

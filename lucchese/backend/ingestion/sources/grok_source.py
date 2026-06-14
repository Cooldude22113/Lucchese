"""
ingestion/sources/grok_source.py
Yield raw Grok conversation items (Rule 8).

The Grok export is a single prod-grok-backend.json whose `conversations` key holds
`{conversation, responses}` items. This source streams those items; parsing is
grok_parser's job.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from ingestion.sources.json_source import load_json
from storage.files.import_store import grok_file


def iter_conversations(path: Path | None = None) -> Iterator[dict]:
    """Yield each raw Grok `{conversation, responses}` item from the export."""
    src = path if path is not None else grok_file()
    if src is None:
        return
    data = load_json(src)
    for item in (data or {}).get("conversations", []):
        if isinstance(item, dict):
            yield item

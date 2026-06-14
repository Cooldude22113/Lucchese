"""
ingestion/sources/chatgpt_source.py
Yield raw ChatGPT conversations across the export files (Rule 8).

A ChatGPT export is a set of conversations-*.json files, each a JSON array of
conversation dicts. This source streams every conversation across all files; it
does no parsing (that is chatgpt_parser's job).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from ingestion.sources.json_source import load_json
from storage.files.import_store import list_chatgpt_files


def iter_conversations(files: list[Path] | None = None) -> Iterator[dict]:
    """Yield each raw ChatGPT conversation dict across the export files."""
    for path in files if files is not None else list_chatgpt_files():
        data = load_json(path)
        if isinstance(data, list):
            for conv in data:
                if isinstance(conv, dict):
                    yield conv

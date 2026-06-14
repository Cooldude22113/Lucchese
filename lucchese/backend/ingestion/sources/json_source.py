"""
ingestion/sources/json_source.py
Load raw JSON export files (Rule 8: sources load raw data).

A thin UTF-8 JSON loader shared by the ChatGPT and Grok sources. Reading is always
explicit UTF-8 so the earlier cp1252 console issue cannot corrupt data.
"""

from __future__ import annotations

import json
from pathlib import Path


def load_json(path: str | Path):
    """Load and parse a UTF-8 JSON file; returns the decoded object."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

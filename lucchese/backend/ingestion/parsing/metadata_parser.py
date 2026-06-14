"""
ingestion/parsing/metadata_parser.py
Shared field/timestamp helpers for the ingestion parsers (Rule 8).

Both the ChatGPT and Grok parsers need to turn their native timestamp encodings
into ISO-8601 UTC and to pull values out of nested dicts defensively. Keeping these
here avoids duplicating the quirk-handling in each parser.
"""

from __future__ import annotations

from datetime import datetime, timezone


def epoch_to_iso(value) -> str | None:
    """ChatGPT epoch float/int (seconds) → ISO-8601 UTC. Tolerates None/garbage."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError, OverflowError):
        return None


def mongo_date_to_iso(value) -> str | None:
    """
    Grok Mongo `{"$date": {"$numberLong": "<ms>"}}` (or `{"$date": "<iso>"}`,
    or a raw ms int) → ISO-8601 UTC. Tolerates None and unexpected shapes.
    """
    if value is None:
        return None
    # Already a string: assume ISO-ish, hand back untouched.
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return _ms_to_iso(value)
    if isinstance(value, dict):
        date = value.get("$date", value)
        if isinstance(date, str):
            return date
        if isinstance(date, dict) and "$numberLong" in date:
            return _ms_to_iso(date["$numberLong"])
        if isinstance(date, (int, float)):
            return _ms_to_iso(date)
    return None


def _ms_to_iso(ms) -> str | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000.0, tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError, OverflowError):
        return None


def first(mapping: dict, *keys, default=None):
    """Return the first present, non-None value among keys in a dict."""
    for k in keys:
        if isinstance(mapping, dict) and mapping.get(k) is not None:
            return mapping[k]
    return default


def domain_of(url: str | None) -> str | None:
    """Extract the bare host from a URL, or None."""
    if not url:
        return None
    try:
        from urllib.parse import urlparse

        host = urlparse(url).netloc
        return host[4:] if host.startswith("www.") else host or None
    except ValueError:
        return None

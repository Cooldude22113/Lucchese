"""
ingestion/parsing/parse_errors.py
Typed errors for the ingestion parsers (Rule 8, Rule 15).

Parsers raise these so the pipeline can capture a per-item failure without
aborting the whole run; observability picks them up through import_errors.
"""

from __future__ import annotations


class ParseError(Exception):
    """A single conversation/message could not be parsed."""


class UnknownFormatError(ParseError):
    """The raw payload did not match any known export format."""

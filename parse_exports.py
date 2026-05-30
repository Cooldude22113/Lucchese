"""
parse_exports.py
----------------
Standalone data preparation script. Not part of the live Lucchese server.

Parses ChatGPT and Grok conversation export files.
Writes every extracted message to a single JSONL file (one JSON object per line).
Writes a plain-text log file with per-source statistics and warnings.

Usage:
    python parse_exports.py --chatgpt conversations.json --output exports_parsed.jsonl
    python parse_exports.py --chatgpt conv1.json --chatgpt conv2.json --grok grok_export.json
    python parse_exports.py --chatgpt conversations.json --grok grok_export.json --output out.jsonl --log out.log

Output schema (one object per line):
    {
        "timestamp":       "<ISO 8601 string or null>",
        "role":            "<'user' | 'assistant'>",
        "text":            "<raw message text>",
        "source":          "<'chatgpt' | 'grok'>",
        "conversation_id": "<string>"
    }

INGEST-001 | Pipeline stage: Implementation
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Generator

# ── Constants ─────────────────────────────────────────────────────────────────

RECOGNISED_ROLES = {"user", "assistant"}
DEFAULT_OUTPUT = "exports_parsed.jsonl"
DEFAULT_LOG = "exports_parsed.log"


# ── Schema ────────────────────────────────────────────────────────────────────

def make_message(
    timestamp: str | None,
    role: str,
    text: str,
    source: str,
    conversation_id: str,
) -> dict:
    """Return a canonical message dict conforming to the INGEST-001 output schema."""
    return {
        "timestamp": timestamp,
        "role": role,
        "text": text,
        "source": source,
        "conversation_id": conversation_id,
    }


# ── Timestamp helpers ─────────────────────────────────────────────────────────

def unix_to_iso(ts) -> str | None:
    """Convert a Unix float/int timestamp to an ISO 8601 UTC string. Returns None on failure."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Writer ────────────────────────────────────────────────────────────────────

def write_jsonl_line(f, message_dict: dict) -> None:
    """Serialise message_dict to JSON and write as a single line to open file handle f."""
    f.write(json.dumps(message_dict, ensure_ascii=False) + "\n")


# ── Logger ────────────────────────────────────────────────────────────────────

class RunLogger:
    """
    Accumulates per-source statistics and warning lines.
    Writes WARN lines to both the log file and stderr during processing.
    Writes the summary block at the end of the run.
    """

    def __init__(self, log_path: str):
        self._log_path = log_path
        self._log_f = None
        self._sources: list[dict] = []
        self._current: dict | None = None
        self._total_written = 0

    def open(self):
        try:
            self._log_f = open(self._log_path, "w", encoding="utf-8")
        except OSError as e:
            # Log file failure is not fatal — warn to stderr and continue without log file.
            print(f"WARNING: Could not open log file {self._log_path!r}: {e}", file=sys.stderr)
            self._log_f = None
        self._write(f"Run started: {now_iso()}\n")

    def close(self):
        self._finalise_current()
        self._write_summary()
        if self._log_f:
            self._log_f.close()
            self._log_f = None

    def begin_source(self, source: str, path: str):
        self._finalise_current()
        self._current = {
            "source": source,
            "path": path,
            "conversations_found": 0,
            "messages_extracted": 0,
            "skipped_no_text": 0,
            "skipped_bad_role": 0,
            "skipped_null_timestamp": 0,
            "files_failed": 0,
            "file_fail_reasons": [],
        }

    def _finalise_current(self):
        if self._current is not None:
            self._sources.append(self._current)
            self._current = None

    def incr(self, field: str, n: int = 1):
        if self._current is not None:
            self._current[field] = self._current.get(field, 0) + n

    def record_written(self, n: int = 1):
        self._total_written += n

    def file_failed(self, reason: str):
        if self._current is not None:
            self._current["files_failed"] += 1
            self._current["file_fail_reasons"].append(reason)

    def warn(self, source: str, conversation_id: str, reason: str):
        line = f"WARN [{source}] conversation_id={conversation_id} message skipped: {reason}"
        self._write(line + "\n")
        print(line, file=sys.stderr)

    def _write(self, text: str):
        if self._log_f:
            try:
                self._log_f.write(text)
                self._log_f.flush()
            except OSError:
                pass

    def _write_summary(self):
        lines = ["\n"]
        total_conversations = 0
        total_skipped = 0

        for s in self._sources:
            total_conversations += s["conversations_found"]
            skipped = (
                s["skipped_no_text"]
                + s["skipped_bad_role"]
                + s["skipped_null_timestamp"]
            )
            total_skipped += skipped

            lines.append(f"Source: {s['source']} | file: {s['path']}")
            lines.append(f"  Conversations found: {s['conversations_found']}")
            lines.append(f"  Messages extracted: {s['messages_extracted']}")
            lines.append(f"  Messages skipped (no text): {s['skipped_no_text']}")
            lines.append(f"  Messages skipped (unrecognised role): {s['skipped_bad_role']}")
            lines.append(f"  Messages skipped (null timestamp, used fallback): {s['skipped_null_timestamp']}")
            lines.append(f"  Files failed: {s['files_failed']}")
            if s["file_fail_reasons"]:
                for r in s["file_fail_reasons"]:
                    lines.append(f"    - {r}")
            lines.append("")

        lines.append(f"Total messages written: {self._total_written}")
        lines.append(f"Total conversations processed: {total_conversations}")
        lines.append(f"Total messages skipped: {total_skipped}")
        if self._total_written == 0:
            lines.append("WARNING: No messages were written to output.")
        lines.append(f"Run completed: {now_iso()}")

        summary = "\n".join(lines) + "\n"
        self._write(summary)
        # Also print summary to stdout.
        print(summary)


# ── ChatGPT handler ───────────────────────────────────────────────────────────

def parse_chatgpt(
    path: str,
    logger: RunLogger,
) -> Generator[dict, None, None]:
    """
    Generator. Parses a ChatGPT conversations.json export file.

    Input structure:
        JSON array of conversation objects. Each conversation has:
            - "id": string (conversation UUID)
            - "create_time": float (Unix timestamp, conversation level)
            - "mapping": dict of node_id → node
                Each node may have a "message" field:
                    - "author": {"role": string}
                    - "create_time": float or null
                    - "content": {"content_type": string, "parts": list}

    Traverses mapping values (not a flat array). Skips null messages,
    system/tool roles, non-text content types, and empty-text messages.
    Yields conforming message dicts.
    """
    logger.begin_source("chatgpt", path)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        reason = f"File not found: {path}"
        logger.file_failed(reason)
        print(f"ERROR: {reason}", file=sys.stderr)
        return
    except json.JSONDecodeError as e:
        reason = f"JSON parse failure: {e}"
        logger.file_failed(reason)
        print(f"ERROR [{path}]: {reason}", file=sys.stderr)
        return

    if not isinstance(data, list):
        reason = "Top-level structure is not a JSON array."
        logger.file_failed(reason)
        print(f"ERROR [{path}]: {reason}", file=sys.stderr)
        return

    for conv_index, conversation in enumerate(data):
        if not isinstance(conversation, dict):
            continue

        conversation_id = conversation.get("id")
        if not conversation_id:
            conversation_id = f"chatgpt_{conv_index}"

        conv_timestamp_raw = conversation.get("create_time")
        conv_timestamp_iso = unix_to_iso(conv_timestamp_raw)

        mapping = conversation.get("mapping")
        if not isinstance(mapping, dict):
            continue

        logger.incr("conversations_found")

        for node_id, node in mapping.items():
            if not isinstance(node, dict):
                continue

            message = node.get("message")
            if not message or not isinstance(message, dict):
                continue

            # Role
            author = message.get("author")
            if not isinstance(author, dict):
                continue
            role = author.get("role", "")
            if role in ("system", "tool"):
                continue
            if role not in RECOGNISED_ROLES:
                logger.warn("chatgpt", conversation_id, f"unrecognised role: {role!r}")
                logger.incr("skipped_bad_role")
                continue

            # Timestamp
            msg_ts_raw = message.get("create_time")
            timestamp_iso = unix_to_iso(msg_ts_raw)
            if timestamp_iso is None:
                # Fall back to conversation-level timestamp.
                timestamp_iso = conv_timestamp_iso
                if timestamp_iso is None:
                    logger.warn("chatgpt", conversation_id, "no timestamp available, writing null")
                    logger.incr("skipped_null_timestamp")
                # null is acceptable — written as null in output.

            # Content
            content = message.get("content")
            if not isinstance(content, dict):
                logger.warn("chatgpt", conversation_id, "message has no content dict")
                logger.incr("skipped_no_text")
                continue

            content_type = content.get("content_type")
            if content_type != "text":
                # Non-text content (images, attachments etc.) — skip silently.
                continue

            parts = content.get("parts", [])
            if not isinstance(parts, list):
                logger.warn("chatgpt", conversation_id, "content.parts is not a list")
                logger.incr("skipped_no_text")
                continue

            # Join only string parts; skip non-string parts (image refs etc.).
            text_parts = [p for p in parts if isinstance(p, str)]
            text = " ".join(text_parts).strip()

            if not text:
                logger.warn("chatgpt", conversation_id, "no extractable text after joining parts")
                logger.incr("skipped_no_text")
                continue

            logger.incr("messages_extracted")
            yield make_message(
                timestamp=timestamp_iso,
                role=role,
                text=text,
                source="chatgpt",
                conversation_id=conversation_id,
            )


# ── Grok handler ──────────────────────────────────────────────────────────────

# Observed format (confirmed from prod-grok-backend.json inspection):
#
# Top-level JSON object with keys: conversations, projects, tasks, media_posts.
# Only "conversations" is consumed here. "media_posts" is ignored.
#
# conversations: array of objects, each:
#   {
#     "conversation": {
#       "id":           "<UUID string>",
#       "create_time":  "<ISO 8601 string with Z suffix>",   ← plain string, NOT MongoDB format
#       "title":        "<string>",
#       "leaf_response_id": null,    ← always null in this export; cannot use as shortcut
#       ...
#     },
#     "responses": [
#       {
#         "response": {
#           "_id":                "<UUID string>",
#           "conversation_id":    "<UUID string>",
#           "sender":             "human" | "assistant" | "ASSISTANT",   ← case varies
#           "message":            "<plain string>",   ← never null; may be empty string
#           "create_time":        {"$date": {"$numberLong": "<ms epoch as string>"}},
#           "parent_response_id": "<UUID string>" | null,
#           "metadata":           {...},
#           "model":              "<string>"
#         },
#         "share_link": ...
#       },
#       ...
#     ]
#   }
#
# Branching: 208 of 210 conversations have branching (parent_response_id set on
# most responses). leaf_response_id is always null — no shortcut available.
# Resolution strategy (from ingest_grok_v2.py): walk the response graph, find
# the leaf node with the highest create_time epoch, walk back to root via
# parent_response_id, reverse to chronological order. This yields the accepted
# (most recently continued) branch.
#
# Role normalisation: "human" → "user"; "assistant" / "ASSISTANT" → "assistant".
#
# Grok occasionally emits <grok:render ...> tags (paired and self-closing) in
# assistant messages. These are stripped before writing to output.

_GROK_PAIRED_RE      = re.compile(r"<grok:[^>]+>.*?</grok:[^>]+>", re.DOTALL)
_GROK_SELFCLOSING_RE = re.compile(r"<grok:[^/][^>]*/?>|<grok:[^>]+/>")


def _grok_clean(text: str) -> str:
    """Strip Grok render tags and normalise whitespace."""
    cleaned = _GROK_PAIRED_RE.sub("", text)
    cleaned = _GROK_SELFCLOSING_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _grok_parse_message_timestamp(create_time) -> str | None:
    """
    Parse Grok response-level create_time.
    Format: {"$date": {"$numberLong": "<ms epoch as string>"}}
    Returns ISO 8601 UTC string, or None on failure.
    """
    if not isinstance(create_time, dict):
        return None
    inner = create_time.get("$date", {})
    if not isinstance(inner, dict):
        return None
    ms_str = inner.get("$numberLong", "")
    if not ms_str:
        return None
    try:
        return datetime.fromtimestamp(int(ms_str) / 1000, tz=timezone.utc).isoformat()
    except (ValueError, OSError):
        return None


def _grok_resolve_accepted_path(responses: list) -> list[dict]:
    """
    Resolve the accepted conversation path from a flat response list.

    Grok exports all branches as a flat list. leaf_response_id is always null.
    Strategy: find the leaf with the highest create_time epoch, walk back via
    parent_response_id to root, reverse to get chronological order.

    Returns a list of response dicts (the inner "response" objects) in
    chronological order representing the accepted path.
    """
    if not responses:
        return []

    id_to_resp: dict[str, dict] = {}
    children_of: dict[str, list] = {}

    for r in responses:
        resp = r.get("response", {})
        rid = resp.get("_id")
        pid = resp.get("parent_response_id")
        if not rid:
            continue
        id_to_resp[rid] = resp
        children_of.setdefault(pid, [])
        children_of.setdefault(rid, [])
        if pid:
            children_of[pid].append(rid)

    all_ids = set(id_to_resp.keys())
    leaf_ids = [rid for rid in all_ids if not children_of.get(rid)]

    if not leaf_ids:
        # Fallback: treat last response as leaf.
        last = responses[-1].get("response", {})
        last_id = last.get("_id")
        if last_id:
            leaf_ids = [last_id]
        else:
            return []

    def leaf_epoch(rid: str) -> int:
        ct = id_to_resp.get(rid, {}).get("create_time", {})
        if isinstance(ct, dict):
            inner = ct.get("$date", {})
            if isinstance(inner, dict):
                try:
                    return int(inner.get("$numberLong", 0))
                except (ValueError, TypeError):
                    return 0
        return 0

    leaf_id = max(leaf_ids, key=leaf_epoch)

    path: list[dict] = []
    node_id: str | None = leaf_id
    visited: set[str] = set()

    while node_id and node_id not in visited:
        visited.add(node_id)
        resp = id_to_resp.get(node_id)
        if resp:
            path.append(resp)
        node_id = resp.get("parent_response_id") if resp else None

    path.reverse()
    return path


def parse_grok(
    path: str,
    logger: RunLogger,
) -> Generator[dict, None, None]:
    """
    Generator. Parses a Grok conversation export JSON file.
    Yields conforming message dicts per the INGEST-001 canonical schema.
    """
    logger.begin_source("grok", path)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        reason = f"File not found: {path}"
        logger.file_failed(reason)
        print(f"ERROR: {reason}", file=sys.stderr)
        return
    except json.JSONDecodeError as e:
        reason = f"JSON parse failure: {e}"
        logger.file_failed(reason)
        print(f"ERROR [{path}]: {reason}", file=sys.stderr)
        return

    if not isinstance(data, dict):
        reason = "Top-level structure is not a JSON object."
        logger.file_failed(reason)
        print(f"ERROR [{path}]: {reason}", file=sys.stderr)
        return

    conversations = data.get("conversations", [])
    if not isinstance(conversations, list):
        reason = "'conversations' key is missing or not an array."
        logger.file_failed(reason)
        print(f"ERROR [{path}]: {reason}", file=sys.stderr)
        return

    for conv_index, conv in enumerate(conversations):
        if not isinstance(conv, dict):
            continue

        conv_meta = conv.get("conversation", {})
        if not isinstance(conv_meta, dict):
            continue

        conversation_id = conv_meta.get("id")
        if not conversation_id:
            conversation_id = f"grok_{conv_index}"

        # Conversation-level timestamp is a plain ISO string with Z suffix.
        conv_ts_raw = conv_meta.get("create_time", "")
        conv_ts_iso = conv_ts_raw.replace("Z", "+00:00") if conv_ts_raw else None

        responses = conv.get("responses", [])
        if not isinstance(responses, list) or not responses:
            continue

        logger.incr("conversations_found")

        accepted_path = _grok_resolve_accepted_path(responses)

        for resp in accepted_path:
            # Role normalisation: human → user; assistant / ASSISTANT → assistant.
            sender = resp.get("sender", "")
            sender_lower = sender.lower()
            if sender_lower == "human":
                role = "user"
            elif sender_lower == "assistant":
                role = "assistant"
            else:
                logger.warn("grok", conversation_id, f"unrecognised sender: {sender!r}")
                logger.incr("skipped_bad_role")
                continue

            # Timestamp: MongoDB extended JSON format at response level.
            timestamp_iso = _grok_parse_message_timestamp(resp.get("create_time"))
            if timestamp_iso is None:
                # Fall back to conversation-level timestamp.
                timestamp_iso = conv_ts_iso
                if timestamp_iso is None:
                    logger.warn("grok", conversation_id, "no timestamp available, writing null")
                logger.incr("skipped_null_timestamp")

            # Text: plain string; strip Grok render tags.
            raw_text = resp.get("message", "")
            if not isinstance(raw_text, str):
                logger.warn("grok", conversation_id, "message field is not a string")
                logger.incr("skipped_no_text")
                continue

            text = _grok_clean(raw_text).strip()
            if not text:
                logger.warn("grok", conversation_id, "empty message after cleaning")
                logger.incr("skipped_no_text")
                continue

            logger.incr("messages_extracted")
            yield make_message(
                timestamp=timestamp_iso,
                role=role,
                text=text,
                source="grok",
                conversation_id=conversation_id,
            )


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse ChatGPT and Grok export files to a canonical JSONL format."
    )
    parser.add_argument(
        "--chatgpt",
        metavar="PATH",
        action="append",
        default=[],
        help="Path to a ChatGPT conversations.json export. Repeatable.",
    )
    parser.add_argument(
        "--grok",
        metavar="PATH",
        action="append",
        default=[],
        help="Path to a Grok export file. Repeatable.",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        default=DEFAULT_OUTPUT,
        help=f"Output JSONL file path. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--log",
        metavar="PATH",
        default=DEFAULT_LOG,
        help=f"Log file path. Default: {DEFAULT_LOG}",
    )
    parser.add_argument(
        "--limit",
        metavar="N",
        type=int,
        default=None,
        help="Stop after writing N messages total. For test runs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Require at least one source.
    if not args.chatgpt and not args.grok:
        print("ERROR: No input files specified. Use --chatgpt and/or --grok.", file=sys.stderr)
        return 1

    logger = RunLogger(args.log)
    logger.open()

    # Open output file. Fatal if this fails.
    try:
        out_f = open(args.output, "w", encoding="utf-8")
    except OSError as e:
        print(f"ERROR: Cannot open output file {args.output!r}: {e}", file=sys.stderr)
        logger.close()
        return 1

    limit = args.limit
    written = 0
    fatal = False
    try:
        # ChatGPT sources.
        for path in args.chatgpt:
            path = os.path.realpath(path)
            for message in parse_chatgpt(path, logger):
                write_jsonl_line(out_f, message)
                logger.record_written()
                written += 1
                if limit and written >= limit:
                    break
            if limit and written >= limit:
                break

        # Grok sources.
        if not (limit and written >= limit):
            for path in args.grok:
                path = os.path.realpath(path)
                for message in parse_grok(path, logger):
                    write_jsonl_line(out_f, message)
                    logger.record_written()
                    written += 1
                    if limit and written >= limit:
                        break
                if limit and written >= limit:
                    break

    except OSError as e:
        print(f"ERROR: Output write failure: {e}", file=sys.stderr)
        fatal = True
    finally:
        out_f.close()

    if limit and written >= limit:
        print(f"[--limit {limit}] reached — stopping early.")

    logger.close()

    if fatal:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
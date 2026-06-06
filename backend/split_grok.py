"""
split_grok.py
─────────────
Splits a large Grok export JSON into individual conversation files.
Skips conversations with no responses/messages.

USAGE:
    python split_grok.py --input "C:/prod-grok-backend.json"
    python split_grok.py --input "C:/prod-grok-backend.json" --output "C:/grok_split"
    python split_grok.py --input "C:/prod-grok-backend.json" --limit 50   # test first 50

OUTPUT:
    One JSON file per conversation in the output folder.
    A summary file: _summary.json with stats and a list of all conversations.
    Skipped (empty) conversations are logged but not written.
"""

import json
import argparse
import os
from pathlib import Path
from datetime import datetime


def parse_messages(conversation: dict) -> list[dict]:
    """
    Extract clean user/assistant message pairs from a Grok conversation.
    Handles the nested response structure Grok uses.
    """
    messages = []
    responses = conversation.get("responses", [])

    for response in responses:
        # Each response has a human turn and a model turn
        human_parts = response.get("humanTurn", {})
        model_parts  = response.get("modelResponses", [])

        user_text = ""
        if isinstance(human_parts, dict):
            user_text = human_parts.get("text", "") or ""
        elif isinstance(human_parts, str):
            user_text = human_parts

        assistant_text = ""
        if model_parts and isinstance(model_parts, list):
            # Take the last model response (most complete)
            last = model_parts[-1]
            if isinstance(last, dict):
                assistant_text = last.get("text", "") or ""
            elif isinstance(last, str):
                assistant_text = last

        # Skip turns where both sides are empty
        user_text      = user_text.strip()
        assistant_text = assistant_text.strip()

        if not user_text and not assistant_text:
            continue

        messages.append({
            "role_user":      user_text,
            "role_assistant": assistant_text,
        })

    return messages


def split_grok(input_path: str, output_dir: str, limit: int | None = None) -> None:
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nGrok Export Splitter")
    print(f"{'─'*60}")
    print(f"Input  : {input_path}")
    print(f"Output : {output_dir}")
    print(f"Limit  : {limit or 'none'}")
    print(f"{'─'*60}\n")

    if not input_path.exists():
        print(f"ERROR: File not found: {input_path}")
        return

    print(f"Loading {input_path.name} ({input_path.stat().st_size / 1_048_576:.1f} MB)...")

    with open(input_path, "r", encoding="utf-8", errors="replace") as f:
        raw = json.load(f)

    # Handle both root formats: {"conversations": [...]} or [...]
    if isinstance(raw, dict) and "conversations" in raw:
        conversations = raw["conversations"]
    elif isinstance(raw, list):
        conversations = raw
    else:
        print(f"ERROR: Unrecognised root format — expected list or {{conversations: []}}")
        return

    total_found = len(conversations)
    print(f"Found {total_found:,} conversations in export\n")

    if limit:
        conversations = conversations[:limit]
        print(f"[TEST MODE] Processing first {limit} conversations\n")

    stats = {
        "total_found":    total_found,
        "processed":      0,
        "written":        0,
        "skipped_empty":  0,
        "skipped_error":  0,
    }

    summary_entries = []

    for i, entry in enumerate(conversations):
        stats["processed"] += 1

        try:
            # Grok wraps each item in a "conversation" key
            conv = entry.get("conversation", entry)

            conv_id    = conv.get("id", f"unknown_{i}")
            title      = conv.get("title", "")
            created_at = conv.get("create_time") or conv.get("createTime", "")
            modified_at = conv.get("modify_time") or conv.get("modifyTime", "")

            messages = parse_messages(entry)

            if not messages:
                stats["skipped_empty"] += 1
                if i < 20 or i % 100 == 0:
                    print(f"  [{i+1:>5}] SKIP (empty)  {conv_id[:40]}")
                continue

            out = {
                "source":      "grok",
                "conv_id":     conv_id,
                "title":       title,
                "created_at":  created_at,
                "modified_at": modified_at,
                "message_count": len(messages),
                "messages":    messages,
            }

            # Sanitise conv_id for use as filename
            safe_id = conv_id.replace("/", "_").replace("\\", "_")[:80]
            out_path = output_dir / f"grok_{safe_id}.json"

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)

            stats["written"] += 1
            summary_entries.append({
                "conv_id":       conv_id,
                "title":         title,
                "created_at":    created_at,
                "message_count": len(messages),
                "file":          out_path.name,
            })

            if i < 20 or i % 100 == 0:
                print(f"  [{i+1:>5}] OK  {len(messages):>3} messages  {title[:50]}")

        except Exception as e:
            stats["skipped_error"] += 1
            print(f"  [{i+1:>5}] ERROR: {e}")

    # Write summary
    summary = {
        "generated_at": datetime.utcnow().isoformat(),
        "source_file":  str(input_path),
        "stats":        stats,
        "conversations": summary_entries,
    }
    summary_path = output_dir / "_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'─'*60}")
    print(f"Done")
    print(f"  Total found   : {stats['total_found']:,}")
    print(f"  Written       : {stats['written']:,}")
    print(f"  Skipped empty : {stats['skipped_empty']:,}")
    print(f"  Skipped error : {stats['skipped_error']:,}")
    print(f"\n  Output folder : {output_dir}")
    print(f"  Summary file  : {summary_path}")
    print(f"{'─'*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Split Grok export JSON into individual conversation files.")
    parser.add_argument("--input",  required=True, help="Path to Grok export JSON file")
    parser.add_argument("--output", default="C:/grok_split", help="Output directory (default: C:/grok_split)")
    parser.add_argument("--limit",  type=int, default=None, help="Only process first N conversations (for testing)")
    args = parser.parse_args()

    split_grok(args.input, args.output, args.limit)


if __name__ == "__main__":
    main()
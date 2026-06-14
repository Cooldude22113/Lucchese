"""
scripts/import_chatgpt.py
Manual import entrypoint (Rule 18: scripts call real modules, not core logic).

Run from backend/ with the venv active. No server required.

    python -m scripts.import_chatgpt [--source chatgpt|grok|all] [--dry-run] [--log PATH]

  --source   Which export to import (default: all).
  --dry-run  Parse and count what WOULD be written, without touching the store.
  --log      Write output to a UTF-8 file as well as the terminal.

Delegates to application.services.import_service.run_import; ensures the runtime
dirs and canonical store schema exist first (via the import flow).
"""

from __future__ import annotations

import argparse
import asyncio
import json

from application.orchestration.import_flow import run_import_flow
from observability.log_context import enable_log


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import raw ChatGPT/Grok exports into the conversation store.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--source", choices=["chatgpt", "grok", "all"], default="all")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and count without writing to the store.")
    parser.add_argument("--log", type=str, default=None, metavar="PATH",
                        help="Write output to a UTF-8 file as well as the terminal.")
    args = parser.parse_args()

    if args.log:
        enable_log(args.log)

    report = asyncio.run(run_import_flow(source=args.source, dry_run=args.dry_run))

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""
documents/lifecycle/cleanup_scheduler.py
Auto-expiry of generated documents (Rule 12).

After a delay, drops the download token and deletes the file from disk.
"""

from __future__ import annotations

import asyncio
import os

from storage.runtime.download_token_store import pop_doc_path


async def schedule_cleanup(token: str, delay_seconds: int = 900) -> None:
    """Delete a generated doc after delay_seconds (default 15 min)."""
    await asyncio.sleep(delay_seconds)
    path = pop_doc_path(token)
    if path and os.path.exists(path):
        os.remove(path)

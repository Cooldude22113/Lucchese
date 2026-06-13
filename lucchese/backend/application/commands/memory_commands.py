"""
application/commands/memory_commands.py
Dispatch explicit memory commands for the chat flow (Rule 4).

Detection lives in memory/commands/detect_memory_command; this dispatches a detected
command to the remember/forget primitives.
"""

from __future__ import annotations

from memory.commands.detect_memory_command import detect_memory_command
from memory.commands.forget import forget
from memory.commands.remember import remember

__all__ = ["detect_memory_command", "handle_memory_command"]


async def handle_memory_command(command: str, content: str, conversation_id: str) -> str:
    """Execute a detected memory command and return the user-facing reply."""
    if command == "remember":
        return await remember(content, conversation_id)
    if command == "forget":
        return await forget(content)
    return ""

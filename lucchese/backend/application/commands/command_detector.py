"""
application/commands/command_detector.py
Detect which chat intercept (if any) a message triggers (Rule 4).

Centralises the intercept ORDER so the chat flow stays readable. Returns
(kind, payload) where kind is one of:
  "shopify" (payload=meal_name) | "memory" (payload=(command, content)) |
  "deal" (payload=message) | "roleplay" | "action_plan" | "scrape" (payload=url) | None
"""

from __future__ import annotations

from application.commands.business_commands import detect_shopify_meal, is_deal_command
from application.commands.roleplay_commands import should_handle_roleplay
from application.commands.scrape_commands import detect_scrape_command
from memory.commands.detect_memory_command import detect_memory_command

_ACTION_PLAN_PHRASES = {"action plan", "action plan.", "action plan!"}


def is_action_plan(message: str) -> bool:
    return message.lower().strip() in _ACTION_PLAN_PHRASES


def detect(message: str, conversation_id: str) -> tuple[str | None, object]:
    """Return (kind, payload) for the first matching intercept, in priority order."""
    meal = detect_shopify_meal(message)
    if meal:
        return "shopify", meal

    command, content = detect_memory_command(message)
    if command:
        return "memory", (command, content)

    if is_deal_command(message):
        return "deal", message

    if should_handle_roleplay(message, conversation_id):
        return "roleplay", None

    if is_action_plan(message):
        return "action_plan", None

    url = detect_scrape_command(message)
    if url:
        return "scrape", url

    return None, None

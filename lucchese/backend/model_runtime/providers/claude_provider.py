"""
model_runtime/providers/claude_provider.py
Low-level Anthropic (Claude) HTTP provider (Rule 5).

The current app uses Anthropic in non-streaming mode and emits the whole reply as
one token chunk. This module owns that single call; the model id, version, URL, and
key all come from config so nothing is hardcoded (B3).
"""

from __future__ import annotations

import httpx

from config.model_settings import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_URL,
    ANTHROPIC_VERSION,
    CLAUDE_MODEL,
    CHAT_MAX_TOKENS,
    LLM_TIMEOUT,
)


async def complete(
    system_prompt: str,
    messages: list[dict],
    max_tokens: int = CHAT_MAX_TOKENS,
    model: str = CLAUDE_MODEL,
    timeout: int = LLM_TIMEOUT,
) -> str:
    """
    Single Anthropic messages call. `messages` must not contain a system role —
    the system prompt is passed separately per the Anthropic API.

    Raises on non-200 so callers surface a clear error.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": messages,
            },
        )
    if res.status_code != 200:
        raise RuntimeError(f"Anthropic API error {res.status_code}: {res.text[:200]}")
    return res.json()["content"][0]["text"]

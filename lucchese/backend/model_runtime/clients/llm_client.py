"""
model_runtime/clients/llm_client.py
Unified chat-model client (Rule 5, Rule 21).

Hides the claude-vs-ollama branch that was previously duplicated across chat.py
(normal / action / scrape), voice.py, and the non-streaming roleplay/summarise
paths. Flows call this; they never touch a provider directly.

Two entry points:
  - complete(): one non-streaming reply string. Works for both providers.
  - stream_tokens(): async generator of token strings. Ollama streams natively;
    Claude (non-streaming in this app) yields its full reply as a single token.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from config.model_settings import (
    CHAT_MAX_TOKENS,
    CHAT_PROVIDER,
    MODEL_FAST,
)
from model_runtime.providers import claude_provider, ollama_provider
from model_runtime.streaming.stream_parser import parse_ollama_line


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """Extract the leading system prompt for the Anthropic API shape."""
    system = ""
    rest: list[dict] = []
    for m in messages:
        if m["role"] == "system" and not system:
            system = m["content"]
        else:
            rest.append(m)
    return system, rest


async def complete(
    messages: list[dict],
    *,
    model: str = MODEL_FAST,
    max_tokens: int = CHAT_MAX_TOKENS,
    provider: str | None = None,
) -> str:
    """Single non-streaming reply, provider chosen by config (or override)."""
    provider = provider or CHAT_PROVIDER
    if provider == "claude":
        system, chat_messages = _split_system(messages)
        return await claude_provider.complete(system, chat_messages, max_tokens=max_tokens)
    return await ollama_provider.complete(messages, model=model)


async def stream_tokens(
    messages: list[dict],
    *,
    model: str = MODEL_FAST,
    max_tokens: int = CHAT_MAX_TOKENS,
    provider: str | None = None,
) -> AsyncIterator[str]:
    """
    Yield reply tokens. For Ollama this is true token streaming; for Claude the
    whole reply arrives as one chunk and is yielded once.
    """
    provider = provider or CHAT_PROVIDER
    if provider == "claude":
        system, chat_messages = _split_system(messages)
        text = await claude_provider.complete(system, chat_messages, max_tokens=max_tokens)
        if text:
            yield text
        return

    async for line in ollama_provider.stream(messages, model=model):
        token, done = parse_ollama_line(line)
        if token:
            yield token
        if done:
            break

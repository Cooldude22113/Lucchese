"""
model_runtime/providers/ollama_provider.py
Low-level Ollama HTTP provider (Rule 5: model-facing work lives in model_runtime).

Exposes two coroutines:
  - complete(messages, model, options)  -> full reply string (stream=False)
  - stream(messages, model)             -> async generator of raw NDJSON lines

Higher layers (llm_client) decide which to call; NDJSON line parsing lives in
model_runtime/streaming/stream_parser.py.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from config.model_settings import OLLAMA_URL, LLM_TIMEOUT


async def complete(
    messages: list[dict],
    model: str,
    options: dict | None = None,
    timeout: int = LLM_TIMEOUT,
) -> str:
    """Single non-streaming Ollama chat call. Returns the message content."""
    payload: dict = {"model": model, "messages": messages, "stream": False}
    if options:
        payload["options"] = options
    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.post(OLLAMA_URL, json=payload)
    return res.json()["message"]["content"]


async def stream(
    messages: list[dict],
    model: str,
    timeout: int = LLM_TIMEOUT,
) -> AsyncIterator[str]:
    """
    Streaming Ollama chat call. Yields raw NDJSON lines as they arrive; the caller
    parses each line with stream_parser.parse_ollama_line().
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            OLLAMA_URL,
            json={"model": model, "messages": messages, "stream": True},
        ) as response:
            async for line in response.aiter_lines():
                if line.strip():
                    yield line

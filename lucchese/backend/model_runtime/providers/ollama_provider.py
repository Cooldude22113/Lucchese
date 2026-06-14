"""
model_runtime/providers/ollama_provider.py
Low-level Ollama HTTP provider (Rule 5: model-facing work lives in model_runtime).

Exposes two coroutines:
  - complete(messages, model, options)  -> full reply string (stream=False)
  - stream(messages, model)             -> async generator of raw NDJSON lines

plus one synchronous connectivity probe:
  - check_availability()                -> (reachable, model_names, detail)

Higher layers (llm_client) decide which to call; NDJSON line parsing lives in
model_runtime/streaming/stream_parser.py.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from config.model_settings import OLLAMA_BASE_URL, OLLAMA_URL, LLM_TIMEOUT


def check_availability(timeout: float = 5.0) -> tuple[bool, list[str], str]:
    """
    Lightweight, synchronous Ollama connectivity probe.

    GETs {OLLAMA_BASE_URL}/api/tags and returns (reachable, model_names, detail).
    Used by observability (startup validation and /health). Never raises: any
    failure is reported as (False, [], detail) so callers degrade gracefully.
    httpx's own timeout guards against a hung daemon, so no thread wrapper is
    needed.
    """
    url = f"{OLLAMA_BASE_URL}/api/tags"
    try:
        res = httpx.get(url, timeout=timeout)
        res.raise_for_status()
        models = [m["name"] for m in res.json().get("models", []) if "name" in m]
        return True, models, f"Ollama reachable at {OLLAMA_BASE_URL} ({len(models)} models)."
    except Exception as exc:
        return False, [], f"Ollama unreachable at {OLLAMA_BASE_URL}: {exc}"


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

"""
config/model_settings.py
Model-facing configuration VALUES only (Rule 16: config stores values; Rule 21:
config must not load heavy models or import providers).

This module holds names, URLs, keys, and tunable limits. The code that actually
calls or loads a model lives in model_runtime/ and reads these constants.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# ── LLM providers ─────────────────────────────────────────────────────────────
OLLAMA_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/api/chat"
MODEL_FAST: str = os.getenv("MODEL_FAST", "gemma2:27b")
MODEL_DEEP: str = os.getenv("MODEL_DEEP", "qwen2.5:32b")

ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
CHAT_PROVIDER: str = os.getenv("CHAT_PROVIDER", "ollama")

# B3: single source of truth for the Claude model id. Previously hardcoded inline
# in chat.py (×3) and voice.py (×1). Override via env without code changes.
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
ANTHROPIC_VERSION: str = "2023-06-01"
ANTHROPIC_URL: str = "https://api.anthropic.com/v1/messages"

# ── Transcription / speech ────────────────────────────────────────────────────
WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "tiny")
ELEVENLABS_TTS_MODEL: str = os.getenv("ELEVENLABS_TTS_MODEL", "eleven_turbo_v2_5")
ELEVENLABS_OUTPUT_FORMAT: str = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128")

# ── Token limits (B4) ─────────────────────────────────────────────────────────
# Previously drifting inline values; named here so they are visible and tunable.
CHAT_MAX_TOKENS: int = 4096      # normal /chat (claude path)
VOICE_MAX_TOKENS: int = 1024     # /voice-chat
ACTION_PLAN_MAX_TOKENS: int = 4096
SCRAPE_REVIEW_MAX_TOKENS: int = 4096

# HTTP timeouts (seconds) for model calls.
LLM_TIMEOUT: int = 300
CLASSIFY_TIMEOUT: int = 30
QUERY_EXPANSION_TIMEOUT: int = 20
SUMMARISE_TIMEOUT: int = 120

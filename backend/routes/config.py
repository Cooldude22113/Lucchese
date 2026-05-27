"""
config.py
Environment variables, API clients, and shared FastAPI dependencies for Lucchese.
Everything that needs to be initialised once at startup and imported everywhere.
"""

import os
import whisper
from dotenv import load_dotenv
from fastapi import Header, HTTPException
from elevenlabs.client import ElevenLabs

load_dotenv()

# ── LLM config ────────────────────────────────────────────────────────────────
OLLAMA_URL        = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/api/chat"
MODEL_FAST        = os.getenv("MODEL_FAST", "gemma2:27b")
MODEL_DEEP        = os.getenv("MODEL_DEEP", "qwen2.5:32b")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CHAT_PROVIDER     = os.getenv("CHAT_PROVIDER", "ollama")

# ── ElevenLabs ────────────────────────────────────────────────────────────────
ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")
el_client           = ElevenLabs(api_key=ELEVENLABS_API_KEY) if ELEVENLABS_API_KEY else None

# ── Whisper ───────────────────────────────────────────────────────────────────
# TODO: upgrade to large-v3 when blocking startup is fixed
whisper_model = whisper.load_model("tiny")

# ── Admin auth ────────────────────────────────────────────────────────────────
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
print(f"[config] ADMIN_API_KEY loaded: {bool(ADMIN_API_KEY)}")


async def verify_admin_key(x_admin_key: str = Header(None)):
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Admin API key not configured")
    if not x_admin_key or x_admin_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin key")
    return x_admin_key

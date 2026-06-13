"""
config/integration_settings.py
Configuration VALUES for external integrations (Rule 11 isolates external systems;
Rule 16 keeps config to values). The clients that consume these live in
integrations/ and model_runtime/providers/.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# ── ElevenLabs (TTS) ──────────────────────────────────────────────────────────
ELEVENLABS_API_KEY: str | None = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID: str | None = os.getenv("ELEVENLABS_VOICE_ID")

# ── Shopify ───────────────────────────────────────────────────────────────────
SHOPIFY_STORE: str | None = os.getenv("SHOPIFY_STORE")
SHOPIFY_CLIENT_ID: str | None = os.getenv("SHOPIFY_CLIENT_ID")
SHOPIFY_CLIENT_SECRET: str | None = os.getenv("SHOPIFY_CLIENT_SECRET")
SHOPIFY_API_VERSION: str = os.getenv("SHOPIFY_API_VERSION", "2026-04")
SHOPIFY_BASE_URL: str = (
    f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}"
    if SHOPIFY_STORE
    else ""
)
SHOPIFY_TOKEN_URL: str = (
    f"https://{SHOPIFY_STORE}.myshopify.com/admin/oauth/access_token"
    if SHOPIFY_STORE
    else ""
)

# ── Google Sheets ─────────────────────────────────────────────────────────────
GOOGLE_SHEETS_SCOPES: list[str] = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
GOOGLE_CREDENTIALS_FILE: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
SPREADSHEET_ID: str = os.getenv(
    "SPREADSHEET_ID", "18wRNdcKcrXmK4xNqS1G3_Hn2fRhD_YTli83-ac6o_mk"
)

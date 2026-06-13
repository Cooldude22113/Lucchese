"""
integrations/shopify/token_cache.py
In-memory caching of the Shopify access token (Rule 11).

Wraps auth.fetch_token() with a process-level cache that refreshes 60s before
expiry, and builds the authenticated request headers.
"""

from __future__ import annotations

import time

from integrations.shopify import auth

_token: str | None = None
_token_expires_at: float = 0.0


async def get_token() -> str:
    """Return a valid access token, refreshing it if cached one is near expiry."""
    global _token, _token_expires_at
    if _token and time.time() < _token_expires_at - 60:
        return _token
    access_token, expires_in = await auth.fetch_token()
    _token = access_token
    _token_expires_at = time.time() + expires_in
    return _token


async def get_headers() -> dict:
    """Authenticated JSON headers for Shopify Admin API calls."""
    token = await get_token()
    return {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }

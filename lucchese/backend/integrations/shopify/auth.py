"""
integrations/shopify/auth.py
Shopify OAuth client-credentials token fetch (Rule 11).

Performs the raw token request. Caching lives in token_cache.py so the network
call and the cache policy are separable.
"""

from __future__ import annotations

import httpx

from config.integration_settings import (
    SHOPIFY_CLIENT_ID,
    SHOPIFY_CLIENT_SECRET,
    SHOPIFY_TOKEN_URL,
)


async def fetch_token() -> tuple[str, int]:
    """
    Request a fresh access token. Returns (access_token, expires_in_seconds).
    Raises on a non-2xx response.
    """
    async with httpx.AsyncClient() as client:
        r = await client.post(
            SHOPIFY_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": SHOPIFY_CLIENT_ID,
                "client_secret": SHOPIFY_CLIENT_SECRET,
            },
        )
        r.raise_for_status()
        data = r.json()
    return data["access_token"], data.get("expires_in", 3600)

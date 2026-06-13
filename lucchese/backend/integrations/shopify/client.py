"""
integrations/shopify/client.py
Low-level Shopify Admin API calls (Rule 11).

Owns the HTTP request to create a product. Payload shapes come from
product_payloads.py; auth headers from token_cache.py.
"""

from __future__ import annotations

import httpx

from config.integration_settings import SHOPIFY_BASE_URL
from integrations.shopify.product_payloads import build_product_payload
from integrations.shopify.token_cache import get_headers


async def create_product(title: str, description: str, price: str, tags: list) -> dict:
    """Create a single Shopify product and return the created product dict."""
    payload = build_product_payload(title, description, price, tags)
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{SHOPIFY_BASE_URL}/products.json",
            headers=await get_headers(),
            json=payload,
        )
        r.raise_for_status()
        return r.json()["product"]

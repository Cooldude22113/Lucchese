"""
api/schemas/business.py
Request models for the business endpoints (Shopify, deal analysis).
"""

from __future__ import annotations

from pydantic import BaseModel


class ShopifyMealRequest(BaseModel):
    meal_name: str

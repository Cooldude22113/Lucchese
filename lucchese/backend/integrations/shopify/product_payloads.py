"""
integrations/shopify/product_payloads.py
Shopify product payload builders (Rule 11).

Pure shape construction — no network. Keeps the wire format for product creation
out of the HTTP client and the meal-product orchestration.
"""

from __future__ import annotations


def build_product_payload(title: str, description: str, price: str, tags: list) -> dict:
    """Build the Admin API product creation payload for a PTPREPS meal product."""
    return {
        "product": {
            "title": title,
            "body_html": description,
            "vendor": "PTPREPS",
            "product_type": "Prepared Meals & Entrées",
            "tags": ", ".join(tags),
            "status": "active",
            "variants": [
                {
                    "price": price,
                    "requires_shipping": True,
                    "taxable": True,
                }
            ],
        }
    }


def macro_description(macros: dict) -> str:
    """One-line macro summary used as the product description."""
    return (
        f"{macros['kcal']:.0f} KCAL | {macros['protein']:.0f}G Protein | "
        f"{macros['carbs']:.0f}G Carbs | {macros['fat']:.0f}G Fat"
    )

"""
integrations/shopify/meal_products.py
Create the standard + bulking Shopify products for a meal (Rule 11).

Orchestrates multiple create_product calls for the fixed PTPREPS product variants.
"""

from __future__ import annotations

from integrations.shopify.client import create_product
from integrations.shopify.product_payloads import macro_description


async def create_meal_products(
    meal_name: str,
    standard_macros: dict,
    bulking_macros: dict,
) -> list[dict]:
    """
    Create the four PTPREPS products for a meal (standard/bulking × two title
    variants). Returns a list of {"title", "id"} for the created products.
    """
    std_desc = macro_description(standard_macros)
    blk_desc = macro_description(bulking_macros)

    products_to_create = [
        {"title": f"{meal_name} - Standard",  "desc": std_desc, "price": "5.00", "tags": ["standard", "meal"]},
        {"title": f"{meal_name} -- Standard", "desc": std_desc, "price": "5.00", "tags": ["standard"]},
        {"title": f"{meal_name} - Bulking",   "desc": blk_desc, "price": "7.50", "tags": ["bulking", "meal"]},
        {"title": f"{meal_name} -- Bulking",  "desc": blk_desc, "price": "7.50", "tags": ["bulking"]},
    ]

    created = []
    for p in products_to_create:
        product = await create_product(p["title"], p["desc"], p["price"], p["tags"])
        created.append({"title": product["title"], "id": product["id"]})
        print(f"Created: {product['title']}")

    return created

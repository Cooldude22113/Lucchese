import httpx
import os
import time
from dotenv import load_dotenv

load_dotenv()

SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET")
BASE_URL = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2026-04"

_token = None
_token_expires_at = 0

async def get_token():
    global _token, _token_expires_at
    if _token and time.time() < _token_expires_at - 60:
        return _token
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://{SHOPIFY_STORE}.myshopify.com/admin/oauth/access_token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            }
        )
        r.raise_for_status()
        data = r.json()
        _token = data["access_token"]
        _token_expires_at = time.time() + data.get("expires_in", 3600)
    return _token

async def get_headers():
    token = await get_token()
    return {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }

async def create_product(title: str, description: str, price: str, tags: list) -> dict:
    payload = {
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
            ]
        }
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/products.json",
            headers=await get_headers(),
            json=payload
        )
        r.raise_for_status()
        return r.json()["product"]

async def create_meal_products(meal_name: str, standard_macros: dict, bulking_macros: dict):
    def macro_description(macros):
        return f"{macros['kcal']:.0f} KCAL | {macros['protein']:.0f}G Protein | {macros['carbs']:.0f}G Carbs | {macros['fat']:.0f}G Fat"

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
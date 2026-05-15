import httpx
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
APPSTLE_KEY = os.getenv("APPSTLE_API_KEY")
print(f"Key loaded: {APPSTLE_KEY[:10] if APPSTLE_KEY else 'NOT FOUND'}")
STORE = os.getenv("SHOPIFY_STORE")
BASE = "https://subscription-admin.appstle.com/api/external/v2"
HEADERS = {"X-API-Key": APPSTLE_KEY}

async def main():
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE}/subscription-plans/{STORE}",
            headers=HEADERS
        )
        print(f"Status: {r.status_code}")
        print(r.text[:2000])

asyncio.run(main())
import asyncio, httpx, os
from dotenv import load_dotenv
load_dotenv()

key = os.getenv('ANTHROPIC_API_KEY')
print(f"Key loaded: {bool(key)}, starts with: {key[:10] if key else 'NONE'}")

async def test():
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key': key,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json'
            },
            json={
                'model': 'claude-sonnet-4-5',
                'max_tokens': 100,
                'messages': [{'role': 'user', 'content': 'say hi'}]
            }
        )
        print(f"Status: {r.status_code}")
        print(f"Response: {r.text[:300]}")

asyncio.run(test())
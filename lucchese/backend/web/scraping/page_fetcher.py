"""
web/scraping/page_fetcher.py
Fetch a site (and a few known subpages) and build a review prompt (Rule 14).

B2 fix: homepage_html is a function-local, initialised at the top. The original kept
it as a module-level global that was reassigned inside the function without `global`
— which both caused stale HTML to leak across calls and would raise
UnboundLocalError. As a local it is correct and reset per call.
"""

from __future__ import annotations

import httpx

from web.scraping.html_text_extractor import TextExtractor
from web.scraping.metadata_extractor import extract_meta
from web.scraping.review_prompt import build_review_prompt


async def scrape_and_review(url: str) -> str:
    """Scrape `url` (+ subpages for root domains) and return the review prompt."""
    homepage_html = ""  # B2: per-call local, not a module global

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    base_url = url.rstrip("/")

    # Only crawl subpages for root domains, not app/deep URLs.
    is_root_url = not any(
        x in url for x in ["/apps/", "/collections/", "/pages/", "/products/"]
    )
    if is_root_url:
        sub_pages = [
            "",
            "/collections/menu",
            "/pages/about",
            "/pages/plans",
            "/apps/subscriptions/bb/351gv78o",
            "/apps/bundles/bb/1cpPOEuwgg",
        ]
    else:
        sub_pages = [""]  # Just scrape the exact URL given

    all_content: dict = {}
    seen_sizes: set = set()

    async with httpx.AsyncClient(
        timeout=15,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-GB,en;q=0.9",
        },
    ) as client:
        for path in sub_pages:
            target = base_url + path
            try:
                response = await client.get(target)
                if response.status_code == 200:
                    extractor = TextExtractor()
                    extractor.feed(response.text)
                    text = extractor.get_text()
                    if (path == "" or path == "/") and not homepage_html:
                        homepage_html = response.text
                    size = len(text)
                    if text and size > 100 and size not in seen_sizes:
                        seen_sizes.add(size)
                        all_content[path or "/"] = text[:2000]
                        print(f"Scraped: {target} ({size} chars)")
                    elif size in seen_sizes:
                        print(f"Skipped duplicate: {target}")
            except Exception as e:
                print(f"Skipped {target}: {e}")

    if not all_content:
        return f"Couldn't reach {url} or extract meaningful content."

    combined = ""
    for path, content in all_content.items():
        combined += f"\n\n--- PAGE: {base_url}{path} ---\n{content}"

    meta = extract_meta(homepage_html) if homepage_html else {}
    return build_review_prompt(url, combined, meta)

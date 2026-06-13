"""
web/scraping/metadata_extractor.py
Extract SEO/technical metadata from raw HTML (Rule 14).
"""

from __future__ import annotations

import re


def extract_meta(html: str) -> dict:
    """Extract title, meta description, og tags, heading counts, schema/canonical flags."""
    meta: dict = {}

    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if title_match:
        meta["title"] = title_match.group(1).strip()

    desc_match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    if desc_match:
        meta["meta_description"] = desc_match.group(1).strip()

    og_title = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    if og_title:
        meta["og_title"] = og_title.group(1).strip()

    og_desc = re.search(
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    if og_desc:
        meta["og_description"] = og_desc.group(1).strip()

    meta["h1_count"] = len(re.findall(r"<h1[^>]*>", html, re.IGNORECASE))
    meta["h2_count"] = len(re.findall(r"<h2[^>]*>", html, re.IGNORECASE))
    meta["has_schema"] = "application/ld+json" in html.lower()
    meta["has_canonical"] = 'rel="canonical"' in html.lower()

    return meta

"""
web/scraping/html_text_extractor.py
Strip HTML to readable text (Rule 14).

Skips script/style/nav-type content and preserves heading markers for the review
prompt.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser


class TextExtractor(HTMLParser):
    """HTML -> readable text, preserving [H1]/[H2]/[H3] markers."""

    SKIP_TAGS = {"script", "style", "noscript", "svg", "iframe", "head"}
    BLOCK_TAGS = {"h1", "h2", "h3", "h4", "p", "li", "td", "th", "div", "section", "article"}

    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self._current_tag = ""
        self.chunks: list[str] = []
        self._buf = ""

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        self._current_tag = tag
        if tag in self.BLOCK_TAGS and self._buf.strip():
            self.chunks.append(self._buf.strip())
            self._buf = ""
        if tag in ("h1", "h2", "h3"):
            self._buf += f"\n[{tag.upper()}] "

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        if tag in self.BLOCK_TAGS and self._buf.strip():
            self.chunks.append(self._buf.strip())
            self._buf = ""

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        text = data.strip()
        if text:
            self._buf += " " + text

    def get_text(self) -> str:
        if self._buf.strip():
            self.chunks.append(self._buf.strip())
        raw = "\n".join(self.chunks)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        raw = re.sub(r" {2,}", " ", raw)
        return raw.strip()


def extract_page_text(html: str) -> str:
    """Convenience: parse HTML and return its readable text."""
    extractor = TextExtractor()
    extractor.feed(html)
    return extractor.get_text()

"""
documents/extraction/pdf_extractor.py
Extract plain text from PDF bytes (Rule 12).
"""

from __future__ import annotations

import io


def extract_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF; returns "" on failure (logged)."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)
    except Exception as e:
        print(f"PDF extraction error: {e}")
        return ""

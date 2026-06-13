"""
documents/extraction/text_extractor.py
Dispatch text extraction by file type (Rule 12).
"""

from __future__ import annotations

from documents.extraction.pdf_extractor import extract_pdf


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Extract plain text from a PDF, TXT, or MD file's bytes."""
    if filename.lower().endswith(".pdf"):
        return extract_pdf(file_bytes)
    return file_bytes.decode("utf-8", errors="ignore")

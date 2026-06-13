"""
application/services/upload_service.py
Upload workflow: extract text, ingest to ChromaDB, record in SQLite (Rule 4).
"""

from __future__ import annotations

import uuid

from documents.extraction.text_extractor import extract_text
from memory.ingestion.document_ingestor import ingest_document
from storage.sqlite.repositories.document_repository import save_document_record


def process_upload(contents: bytes, filename: str) -> tuple[dict | None, str | None]:
    """
    Extract → ingest → record an uploaded file.
    Returns (result, None) on success or (None, error_message) if no text extracted.
    """
    text = extract_text(contents, filename)
    if not text.strip():
        return None, "Could not extract text from file"

    doc_id = uuid.uuid4().hex
    chunk_count = ingest_document(doc_id, filename, text)
    file_type = "pdf" if filename.lower().endswith(".pdf") else "text"

    save_document_record(doc_id, filename, file_type, chunk_count)

    return {
        "doc_id": doc_id,
        "filename": filename,
        "chunk_count": chunk_count,
        "message": f"Ingested {chunk_count} chunks from {filename}",
    }, None

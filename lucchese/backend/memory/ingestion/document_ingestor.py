"""
memory/ingestion/document_ingestor.py
Chunk and store an uploaded document into the documents collection (Rule 8).
"""

from __future__ import annotations

from datetime import datetime, timezone

from memory.collections.collection_registry import get_documents
from memory.processing.chunking import chunk_text


def ingest_document(doc_id: str, filename: str, text: str) -> int:
    """Chunk `text` and upsert each chunk; returns the chunk count."""
    chunks = chunk_text(text)
    now = datetime.now(timezone.utc).isoformat()
    col_documents = get_documents()

    for i, chunk in enumerate(chunks):
        col_documents.upsert(
            ids=[f"doc_{doc_id}_chunk_{i}"],
            documents=[chunk],
            metadatas=[{
                "source":     "document",
                "doc_id":     doc_id,
                "filename":   filename,
                "chunk_idx":  str(i),
                "created_at": now,
            }],
        )

    return len(chunks)

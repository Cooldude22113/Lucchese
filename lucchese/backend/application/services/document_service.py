"""
application/services/document_service.py
Document listing, deletion, generation, and download (Rule 4).

Hides the ChromaDB + SQLite + docx-generation details behind stable actions the
document routes call.
"""

from __future__ import annotations

import asyncio

from documents.generation.docx_generator import markdown_to_docx
from documents.lifecycle.cleanup_scheduler import schedule_cleanup
from memory.inspection.memory_delete import delete_document_chunks
from storage.runtime.download_token_store import get_doc_path, store_doc_token
from storage.sqlite.repositories.document_repository import (
    delete_document_record,
    list_documents,
)


def list_docs() -> list[dict]:
    return list_documents()


def delete_document(doc_id: str) -> dict:
    """Remove a document from ChromaDB (chunks) and SQLite (record)."""
    delete_document_chunks(doc_id)
    delete_document_record(doc_id)
    return {"deleted": doc_id}


def generate_doc(content: str, title: str) -> dict:
    """Render markdown to a .docx, issue a download token, schedule cleanup."""
    filepath = markdown_to_docx(content, title)
    token, filename = store_doc_token(filepath)
    asyncio.create_task(schedule_cleanup(token))
    return {"token": token, "filename": filename}


def get_download_path(token: str) -> str | None:
    return get_doc_path(token)

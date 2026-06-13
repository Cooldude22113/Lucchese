"""
storage/sqlite/repositories/document_repository.py
Uploaded-document record persistence for the conversations database (Rule 9).

Stores metadata only — the document chunks live in ChromaDB and the source files
under data/. This repository tracks what was uploaded for listing and deletion.
"""

from __future__ import annotations

from datetime import datetime, timezone

from storage.sqlite.connection import get_con


def save_document_record(doc_id: str, filename: str, file_type: str, chunk_count: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    con = get_con()
    con.execute(
        "INSERT INTO documents (id, filename, file_type, chunk_count, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (doc_id, filename, file_type, chunk_count, now),
    )
    con.commit()
    con.close()


def list_documents() -> list[dict]:
    con = get_con()
    rows = con.execute(
        "SELECT id, filename, file_type, chunk_count, created_at FROM documents "
        "ORDER BY created_at DESC"
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def delete_document_record(doc_id: str) -> None:
    con = get_con()
    con.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    con.commit()
    con.close()

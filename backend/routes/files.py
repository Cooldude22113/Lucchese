"""
routes/files.py
───────────────
File upload, document management, Word doc generation, and health endpoints:

  POST /upload                — upload PDF/TXT/MD, extract text, ingest to ChromaDB
  GET  /documents             — list all uploaded documents
  DELETE /documents/{doc_id} — delete document from ChromaDB + SQLite
  POST /generate-doc          — generate a Word .docx from markdown content
  GET  /download/{token}      — download a generated Word doc by token
  GET  /health                — public health check, no auth required
"""

import io
import os
import uuid
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from pypdf import PdfReader

from routes.memory import col_documents, ingest_document, col_knowledge, col_facts, col_style
from routes.database import save_document_record, list_documents, delete_document_record
from routes.documents import markdown_to_docx, store_doc_token, get_doc_path, schedule_cleanup

router = APIRouter()

# ── Text extraction ───────────────────────────────────────────────────────────
def extract_text(file_bytes: bytes, filename: str) -> str:
    """Extract plain text from PDF, TXT, or MD files."""
    if filename.lower().endswith(".pdf"):
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            pages  = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages)
        except Exception as e:
            print(f"PDF extraction error: {e}")
            return ""
    else:
        return file_bytes.decode("utf-8", errors="ignore")

# ── POST /upload ──────────────────────────────────────────────────────────────
@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Upload a PDF, TXT, or MD file.
    Extracts text, chunks it, and ingests into ChromaDB documents collection.
    Records the document in SQLite for listing and deletion.
    """
    contents = await file.read()
    filename = file.filename or "unknown"

    text = extract_text(contents, filename)
    if not text.strip():
        return JSONResponse({"error": "Could not extract text from file"}, status_code=400)

    doc_id      = uuid.uuid4().hex
    chunk_count = ingest_document(doc_id, filename, text)
    file_type   = "pdf" if filename.lower().endswith(".pdf") else "text"

    save_document_record(doc_id, filename, file_type, chunk_count)

    return {
        "doc_id":      doc_id,
        "filename":    filename,
        "chunk_count": chunk_count,
        "message":     f"Ingested {chunk_count} chunks from {filename}",
    }

# ── GET /documents ────────────────────────────────────────────────────────────
@router.get("/documents")
def list_docs():
    """List all uploaded documents from SQLite."""
    return list_documents()

# ── DELETE /documents/{doc_id} ────────────────────────────────────────────────
@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    """
    Delete a document from both ChromaDB and SQLite.
    ChromaDB deletion removes all chunks; SQLite deletion removes the record.
    """
    try:
        results = col_documents.get(where={"doc_id": doc_id})
        if results["ids"]:
            col_documents.delete(ids=results["ids"])
    except Exception as e:
        print(f"delete_document chroma error: {e}")

    delete_document_record(doc_id)
    return {"deleted": doc_id}

# ── POST /generate-doc ────────────────────────────────────────────────────────
@router.post("/generate-doc")
async def generate_doc(req: dict):
    """
    Called by the frontend when it detects a [GENERATE_DOC: ...] marker.
    Converts markdown content to a .docx file and returns a download token.

    Body: { "content": "...", "title": "..." }
    Returns: { "token": "...", "filename": "..." }
    """
    content = req.get("content", "").strip()
    title   = req.get("title", "document").strip()

    if not content:
        return {"error": "No content provided"}

    try:
        filepath         = markdown_to_docx(content, title)
        token, filename  = store_doc_token(filepath)
        asyncio.create_task(schedule_cleanup(token))
        return {"token": token, "filename": filename}
    except Exception as e:
        print(f"generate_doc error: {e}")
        return {"error": str(e)}

# ── GET /download/{token} ─────────────────────────────────────────────────────
@router.get("/download/{token}")
async def download_doc(token: str):
    """Download a generated .docx by its token. Tokens expire after 15 minutes."""
    filepath = get_doc_path(token)

    if not filepath or not os.path.exists(filepath):
        return JSONResponse(
            {"error": "Document not found or expired"},
            status_code=404
        )

    return FileResponse(
        path       = filepath,
        filename   = Path(filepath).name,
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

# ── GET /health ───────────────────────────────────────────────────────────────
@router.get("/health")
def health():
    """Public health check — returns collection counts. No auth required."""
    return {
        "status":    "ok",
        "knowledge": col_knowledge.count(),
        "facts":     col_facts.count(),
        "style":     col_style.count(),
        "documents": col_documents.count(),
    }

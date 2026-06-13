"""
api/routes/document_routes.py
Thin document endpoints (Rule 2):
  GET    /documents          — list uploaded documents
  DELETE /documents/{doc_id} — delete from ChromaDB + SQLite
  POST   /generate-doc       — markdown -> .docx, returns a download token
  GET    /download/{token}   — download a generated .docx (expires after 15 min)

All logic lives in document_service.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from api.schemas.documents import GenerateDocRequest
from application.services import document_service

router = APIRouter()

_DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


@router.get("/documents")
def list_docs():
    return document_service.list_docs()


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    return document_service.delete_document(doc_id)


@router.post("/generate-doc")
async def generate_doc(req: GenerateDocRequest):
    content = req.content.strip()
    title = req.title.strip()
    if not content:
        return {"error": "No content provided"}
    try:
        return document_service.generate_doc(content, title)
    except Exception as e:
        print(f"generate_doc error: {e}")
        return {"error": str(e)}


@router.get("/download/{token}")
async def download_doc(token: str):
    filepath = document_service.get_download_path(token)
    if not filepath or not os.path.exists(filepath):
        return JSONResponse({"error": "Document not found or expired"}, status_code=404)
    return FileResponse(
        path=filepath,
        filename=Path(filepath).name,
        media_type=_DOCX_MEDIA_TYPE,
    )

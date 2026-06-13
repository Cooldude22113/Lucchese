"""
api/routes/upload_routes.py
Thin upload endpoint (Rule 2). Workflow lives in upload_service.
"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from application.services.upload_service import process_upload

router = APIRouter()


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload a PDF/TXT/MD file: extract text, ingest, and record it."""
    contents = await file.read()
    filename = file.filename or "unknown"

    result, error = process_upload(contents, filename)
    if error:
        return JSONResponse({"error": error}, status_code=400)
    return result

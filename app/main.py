"""ClearDoc API — entry point.

This file defines our web API: the "front door" of the backend.
Run it with:  uvicorn app.main:app --reload
"""

import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile

# The FastAPI application object. Every endpoint below is registered on it.
app = FastAPI(
    title="ClearDoc API",
    description="Understand everyday documents: upload, explain, guide.",
    version="0.1.0",
)

# Where uploaded files are stored for now (local folder).
# Later (cloud phase) this becomes Azure Blob Storage — only this line changes.
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Basic input validation rules — never trust what users send.
ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAX_BYTES = 10 * 1024 * 1024  # 10 MB


@app.get("/health")
def health() -> dict:
    """Liveness check: monitoring systems call this to ask 'are you up?'"""
    return {"status": "ok", "service": "cleardoc-api", "version": "0.1.0"}


@app.post("/documents", status_code=201)
async def upload_document(file: UploadFile = File(...)) -> dict:
    """Accept a document (PDF or photo) and store it.

    Returns a document_id that every later step (OCR, extraction, Q&A)
    will use to refer to this document.
    """
    # 1. Reject types we can't process — 415 = "Unsupported Media Type".
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}. "
            f"Allowed: PDF, JPEG, PNG.",
        )

    # 2. Read the bytes and enforce a size limit — 413 = "Payload Too Large".
    contents = await file.read()
    if len(contents) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB).")

    # 3. Give the document a unique, unguessable ID (never trust filenames:
    #    two users may both upload 'bill.pdf', and filenames can be malicious).
    doc_id = str(uuid.uuid4())
    extension = Path(file.filename or "upload").suffix.lower()
    destination = UPLOAD_DIR / f"{doc_id}{extension}"
    destination.write_bytes(contents)

    # 4. Tell the client what happened, in JSON.
    return {
        "document_id": doc_id,
        "original_filename": file.filename,
        "size_bytes": len(contents),
        "status": "received",
    }

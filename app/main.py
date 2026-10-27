"""ClearDoc API — entry point.

This file defines our web API: the "front door" of the backend.
Run it with:  uvicorn app.main:app --reload
"""

import json
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import extraction, llm, ocr, rag
from app.database import Base, SessionLocal, engine
from app.models import Chunk, Document

# Create any tables that don't exist yet (reads the models' definitions).
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="ClearDoc API",
    description="Understand everyday documents: upload, explain, guide.",
    version="0.2.0",
)

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def get_db():
    """Dependency: hand each request its own database session,
    and guarantee it's closed afterwards, even if the request crashes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health() -> dict:
    """Liveness check: monitoring systems call this to ask 'are you up?'"""
    return {"status": "ok", "service": "cleardoc-api", "version": "0.2.0"}


@app.post("/documents", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    """Accept a document (PDF or photo), store the file, record it in the DB."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}. "
            f"Allowed: PDF, JPEG, PNG.",
        )

    contents = await file.read()
    if len(contents) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB).")

    doc_id = str(uuid.uuid4())
    extension = Path(file.filename or "upload").suffix.lower()
    destination = UPLOAD_DIR / f"{doc_id}{extension}"
    destination.write_bytes(contents)

    # NEW: record the document in the database — the app's memory.
    record = Document(
        id=doc_id,
        original_filename=file.filename or "upload",
        content_type=file.content_type,
        size_bytes=len(contents),
        stored_path=str(destination),
        status="received",
    )
    db.add(record)      # stage the new row
    db.commit()         # actually write it (like Git commit: make it permanent)

    return {
        "document_id": doc_id,
        "original_filename": record.original_filename,
        "size_bytes": record.size_bytes,
        "status": record.status,
    }


@app.post("/documents/{document_id}/ocr")
def run_ocr(document_id: str, db: Session = Depends(get_db)) -> dict:
    """Run OCR on a stored document: pixels in, text out.

    Separate endpoint (instead of OCR-inside-upload) so uploads stay fast
    and OCR failures can be retried without re-uploading.
    """
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if doc.content_type == "application/pdf":
        raise HTTPException(status_code=501, detail="PDF OCR arrives next; images only for now.")

    result = ocr.extract_text(doc.stored_path)

    # Save the outcome + move the bookmark (status) forward.
    doc.raw_text = result["text"]
    doc.ocr_confidence = result["confidence"]
    doc.status = "ocr_done"
    db.commit()

    return {
        "document_id": doc.id,
        "status": doc.status,
        "confidence": result["confidence"],
        "word_count": result["word_count"],
        "text_preview": result["text"][:400],
    }


@app.post("/documents/{document_id}/extract")
def run_extraction(document_id: str, db: Session = Depends(get_db)) -> dict:
    """Turn the OCR text blob into labeled, validated fields (via the LLM)."""
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if doc.status != "ocr_done" or not doc.raw_text:
        raise HTTPException(
            status_code=409,  # 409 Conflict: valid request, wrong state
            detail=f"Document must be OCR'd first (current status: {doc.status}).",
        )

    try:
        fields = extraction.extract_bill_fields(doc.raw_text)
    except ValueError as error:
        raise HTTPException(status_code=502, detail=str(error))

    doc.extracted_fields = fields.model_dump_json()
    doc.status = "extracted"
    db.commit()

    return {
        "document_id": doc.id,
        "status": doc.status,
        "fields": fields.model_dump(),
    }


@app.post("/documents/{document_id}/index")
def index_document(document_id: str, db: Session = Depends(get_db)) -> dict:
    """Chunk the document text and store each chunk with its embedding.
    After this, the document is ready to answer questions."""
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if not doc.raw_text:
        raise HTTPException(status_code=409, detail="Run OCR first.")

    # Re-indexing? Clear old chunks so we never store duplicates.
    db.query(Chunk).filter(Chunk.document_id == document_id).delete()

    embedder = rag.get_embedder()
    pieces = rag.chunk_text(doc.raw_text)
    for position, piece in enumerate(pieces):
        db.add(Chunk(
            id=str(uuid.uuid4()),
            document_id=document_id,
            position=position,
            text=piece,
            embedding=json.dumps(embedder.embed(piece)),
        ))
    doc.status = "ready"
    db.commit()
    return {"document_id": document_id, "chunks_indexed": len(pieces), "status": doc.status}


class AskRequest(BaseModel):
    question: str


@app.post("/documents/{document_id}/ask")
def ask_question(document_id: str, body: AskRequest, db: Session = Depends(get_db)) -> dict:
    """RAG in action: retrieve the relevant chunks, answer ONLY from them."""
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if doc.status != "ready":
        raise HTTPException(status_code=409, detail=f"Index the document first (status: {doc.status}).")

    rows = db.query(Chunk).filter(Chunk.document_id == document_id).all()
    stored = [
        {"text": r.text, "embedding": json.loads(r.embedding), "position": r.position}
        for r in rows
    ]

    retrieved = rag.retrieve(body.question, stored, top_k=3)
    prompt = rag.build_answer_prompt(body.question, retrieved)
    answer = llm.get_llm().complete(prompt)

    return {
        "document_id": document_id,
        "question": body.question,
        "answer": answer,
        # Citations: exactly which excerpts the answer is grounded in.
        "sources": [
            {"excerpt": c["position"], "score": c["score"], "text": c["text"]}
            for c in retrieved
        ],
    }


@app.get("/documents/{document_id}")
def get_document(document_id: str, db: Session = Depends(get_db)) -> dict:
    """Look up ONE document by its id — the payoff of returning document_id."""
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {
        "document_id": doc.id,
        "original_filename": doc.original_filename,
        "content_type": doc.content_type,
        "size_bytes": doc.size_bytes,
        "status": doc.status,
        "created_at": doc.created_at.isoformat(),
    }


@app.get("/documents")
def list_documents(db: Session = Depends(get_db)) -> list[dict]:
    """List recent documents, newest first."""
    docs = db.execute(
        select(Document).order_by(Document.created_at.desc()).limit(50)
    ).scalars()
    return [
        {"document_id": d.id, "original_filename": d.original_filename,
         "status": d.status, "created_at": d.created_at.isoformat()}
        for d in docs
    ]

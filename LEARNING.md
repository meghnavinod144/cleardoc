# Learning log

One entry per build session: what was built, what I learned, what I still
don't fully understand. (Interview gold later. Honesty mandatory.)

## Session 1 — project scaffold & first API endpoints

**Built:** Git repo, FastAPI app with `GET /health` and `POST /documents`
(upload with type + size validation), tested with curl.

**Learned:**
- An API endpoint = URL path + HTTP method + handler function.
- HTTP status codes speak for us: 201 created, 415 wrong type, 413 too large.
- Never trust client input: validate type and size, never use the client's
  filename for storage (collisions + attacks) — generate a UUID instead.
- `.gitignore` keeps user data and secrets out of version control.

**Still unclear:** (fill in after reviewing — e.g. what `async` really does)

## Session 2 — database layer

**Built:** SQLAlchemy + SQLite; Document model (table); upload now writes a
row; new endpoints GET /documents/{id} and GET /documents; 404 handling.

**Learned:**
- A database = the app's structured, searchable memory. Files hold bytes;
  the DB holds facts ABOUT them.
- Table = sheet, row = one record, column = one field. Primary key = the
  unique ID per row (the document_id we return!).
- ORM = translator: Python classes/objects in, SQL out. Same code works on
  SQLite today, PostgreSQL in the cloud phase (change one URL).
- db.add() stages, db.commit() makes permanent (same mental model as Git).
- 404 = "no such resource" — look up, check None, raise HTTPException.

## Session 3 — OCR pipeline

**Built:** app/ocr.py (Tesseract + preprocessing), POST /documents/{id}/ocr,
raw_text + ocr_confidence columns, status moves received → ocr_done.
Tested on a generated sample electricity bill: 95.3% confidence.

**Learned:**
- OCR = pattern recognition on pixels; preprocessing (grayscale,
  autocontrast) improves accuracy on real-world photos.
- Confidence scores let the app KNOW when it read badly (later: ask the
  user for a clearer photo instead of answering from garbage).
- OCR as separate endpoint = uploads stay fast, failures retryable.
- Changing a table's columns in dev = delete the SQLite file; in
  production this needs MIGRATIONS (Alembic) — scheduled for later.

## Session 4 — LLM extraction layer

**Built:** app/llm.py (provider abstraction: AnthropicProvider ready + Mock
for offline dev), app/extraction.py (prompt + Pydantic validation),
POST /documents/{id}/extract, status received → ocr_done → extracted.

**Learned:**
- An LLM API call = an HTTPS POST with the prompt + API key; reply is JSON.
- Abstraction layer: only llm.py knows WHICH provider; swapping models =
  one file. Mock provider = build/test without keys or cost.
- Never trust LLM output: Pydantic validates shape and types; fail loudly.
- Prompts live in code and say: use null, never invent. (Anti-hallucination
  starts in the prompt.)
- 409 Conflict = right request, wrong state (extract before OCR).
- Mock's regex missed consumer_number (label and value on separate lines)
  → honest null, exactly as designed. The real LLM handles layout quirks.

## Session 5 — RAG: retrieval-augmented generation

**Built:** app/rag.py (chunking, embeddings via MockEmbedder, cosine
similarity, retrieval, answer prompt), Chunk table (our vector store),
POST /documents/{id}/index and /ask with citations. Status → ready.

**Learned:**
- RAG = open-book exam: retrieve relevant chunks, LLM answers ONLY from them.
- Chunking: split by lines into ~240-char pieces so retrieval is precise.
- Embedding = text → vector (list of numbers); similar meaning → nearby
  vectors. Mock: hashed word counts (word overlap). Real: semantic API.
- Cosine similarity = the one formula behind "vector search".
- Citations (sources with scores) come free from retrieval — show them.
- Retrieval test: "due date + total" question correctly ranked the
  TOTAL/due-date chunk first (0.387 vs 0.191 vs 0.083).

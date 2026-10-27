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

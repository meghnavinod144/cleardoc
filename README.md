# ClearDoc

An AI assistant for the documents of everyday life — lab reports, utility bills,
certificates, agreements. Upload a document, get it explained in your own
language (text or voice), with honest insights and concrete next steps.

**Status:** v0.1 — core API under construction (sprint day 1).

## Architecture

One country-neutral **core engine** (upload → OCR → classify → extract → RAG
answer) plus **plug-in document modules** that carry only their own extraction
rules and advice content. Launch modules: utility bills, medical lab reports.

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
# open http://localhost:8000/docs for the interactive API documentation
```

## API so far

| Method | Path        | Purpose                              |
|--------|-------------|--------------------------------------|
| GET    | /health     | Liveness check                       |
| POST   | /documents  | Upload a PDF/JPEG/PNG (max 10 MB)    |

## Learning log

See `LEARNING.md` — this project is built learn-first, on purpose.

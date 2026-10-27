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

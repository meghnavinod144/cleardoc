"""Diagnostic probe: the EXACT call our GeminiProvider makes, isolated.

curl in the same CI run gets 200; the app's urllib call gets 404.
This prints what Python sees (key length, response or full error body)
so the difference has nowhere to hide.
"""

import os
import urllib.request

key = os.environ.get("GEMINI_API_KEY", "")
print("python sees key length:", len(key), "tail:", repr(key[-3:]) if key else "EMPTY")

req = urllib.request.Request(
    "https://generativelanguage.googleapis.com/v1beta/models",
    headers={"x-goog-api-key": key},
)
try:
    with urllib.request.urlopen(req, timeout=30) as response:
        print("python urllib status:", response.status)
        print("first bytes:", response.read(120))
except Exception as error:
    print("python urllib error:", error)
    body = getattr(error, "read", lambda: b"")()
    print("error body:", body[:300])
    print("error headers:", dict(getattr(error, "headers", {}) or {}))

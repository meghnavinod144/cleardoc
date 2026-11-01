"""The LLM layer — ClearDoc's rented brain, behind our own abstraction.

KEY DESIGN DECISION: no other file in this project is allowed to know
WHICH LLM provider we use. They all call `get_llm().complete(...)`.
Why? Providers change prices and models constantly; with this one-file
abstraction, switching Claude → GPT → Gemini means editing ONE class —
the rest of ClearDoc never notices. (Same trick as database.py.)

The API key is read from the environment (.env), NEVER written in code.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request


class AnthropicProvider:
    """Talks to the real Claude API over HTTPS.

    One API call = one HTTPS POST to api.anthropic.com with:
      - our API key in a header (proves who is paying)
      - the prompt as JSON
    and the model's reply comes back as JSON. That's all an "LLM API" is.
    """

    API_URL = "https://api.anthropic.com/v1/messages"
    MODEL = "claude-haiku-4-5"  # small+cheap tier: extraction doesn't need the giant model

    def __init__(self, api_key: str):
        self.api_key = api_key

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        payload = {
            "model": self.MODEL,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        request = urllib.request.Request(
            self.API_URL,
            data=json.dumps(payload).encode(),
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.load(response)
        return body["content"][0]["text"]


class GeminiProvider:
    """Talks to Google's Gemini API — the free-tier brain.

    Same shape as AnthropicProvider: HTTPS POST, key in a header,
    prompt in, text out. Different provider, same socket.
    """

    API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

    def _discover_model(self) -> str:
        """Ask Google which models THIS key can use, pick a flash one.

        Model names change often; discovering beats hard-coding. A failure
        here also reveals key problems precisely (the list call's error)."""
        request = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": self.api_key},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.load(response)
        usable = [m["name"].split("/")[-1] for m in body.get("models", [])
                  if "generateContent" in m.get("supportedGenerationMethods", [])]
        preferred = [m for m in usable if "flash" in m
                     and not any(x in m for x in ("image", "live", "tts", "audio"))]
        if not (preferred or usable):
            raise RuntimeError("Key valid but no usable Gemini models listed.")
        return (preferred or usable)[0]

    def complete(self, prompt: str, max_tokens: int = 2048) -> str:
        # thinkingBudget 0 asks newer Gemini models to answer directly
        # instead of "thinking" first — extraction and grounded Q&A don't
        # need deliberation, and it cuts latency dramatically.
        generation_config = {"maxOutputTokens": max_tokens,
                             "thinkingConfig": {"thinkingBudget": 0}}

        def call(model: str, config: dict) -> dict:
            payload = {"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": config}
            request = urllib.request.Request(
                self.API_URL.format(model=model),
                data=json.dumps(payload).encode(),
                headers={"x-goog-api-key": self.api_key,
                         "content-type": "application/json"},
            )
            # 120s: free-tier requests can queue behind rate limits.
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.load(response)

        def attempt(config: dict) -> dict:
            try:
                return call(self.model, config)
            except urllib.error.HTTPError as error:
                if error.code == 404:  # model unknown → discover, retry once
                    self.model = self._discover_model()
                    return call(self.model, config)
                if error.code == 429:  # rate limited → wait politely, retry once
                    time.sleep(35)
                    return call(self.model, config)
                detail = error.read().decode(errors="replace")[:300]
                raise RuntimeError(f"Gemini HTTP {error.code}: {detail}") from error

        try:
            body = attempt(generation_config)
        except RuntimeError as error:
            # Older models reject thinkingConfig → retry plain once.
            if "thinking" in str(error).lower():
                body = attempt({"maxOutputTokens": max_tokens})
            else:
                raise
        except (urllib.error.URLError, TimeoutError, OSError):
            body = attempt(generation_config)  # one retry on timeout/network

        # Tolerant reply parsing: thinking models may return several parts.
        parts = body["candidates"][0]["content"].get("parts", [])
        texts = [p["text"] for p in parts if "text" in p]
        if not texts:
            raise RuntimeError(f"Gemini returned no text: {json.dumps(body)[:200]}")
        return "\n".join(texts)


class MockProvider:
    """A PRETEND LLM for offline development — no API key, no cost.

    It only knows how to do one trick: find bill fields in OCR text with
    simple pattern matching. Good enough to build and test the pipeline's
    SHAPE; the real provider plugs in later with zero code changes.
    (This is also how automated tests will run without paying per test.)
    """

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        # Crude Q&A mode: when the prompt is a RAG answer-prompt, reply by
        # pointing at the most relevant excerpt (a real LLM writes prose).
        if "DOCUMENT EXCERPTS:" in prompt and "QUESTION:" in prompt:
            excerpts_part = prompt.split("DOCUMENT EXCERPTS:")[1].split("QUESTION:")[0]
            first_excerpt = excerpts_part.strip().split("---")[0].strip()
            return (
                "Based on your document, the most relevant information is:\n"
                f"{first_excerpt}\n"
                "(MockProvider: plug in a real API key for a proper answer.)"
            )

        text = prompt  # extraction mode: the OCR text is embedded in the prompt

        def find(pattern):
            match = re.search(pattern, text)
            return match.group(1).strip() if match else None

        def number(value):
            return float(value.replace(",", "")) if value else None

        # Lab-report extraction (the prompt carries the module's instructions)
        if "medical lab report" in text:
            tests = []
            row = re.compile(
                r"^([A-Za-z][A-Za-z ()/-]+?)\s+([\d.]+)\s+(\S+)\s+Ref:\s*([\d.]+\s*-\s*[\d.]+)\s*(LOW|HIGH|NORMAL)?",
                re.MULTILINE,
            )
            for m in row.finditer(text):
                tests.append({
                    "name": m.group(1).strip(), "value": float(m.group(2)),
                    "unit": m.group(3), "reference_range": m.group(4).replace(" ", ""),
                    "flag": m.group(5),
                })
            fields = {
                "patient_name": find(r"Patient Name\s*:?\s+(.+)"),
                "report_date": find(r"Report Date\s*:?\s+(.+)"),
                "lab_name": find(r"^([A-Z][A-Za-z ]+LABORATOR\w*)"),
                "tests": tests,
            }
            return json.dumps(fields)

        # Utility-bill extraction
        fields = {
            "consumer_number": find(r"Consumer Number\s*:?\s*\n?\s*(\d+)"),
            "billing_period": find(r"Billing Period\s*:?\s+(.+)"),
            "due_date": find(r"Due Date\s*:?\s+(.+)"),
            "units_consumed_kwh": number(find(r"Units Consumed\s*:?\s+([\d,]+)")),
            "total_amount_rs": number(find(r"TOTAL AMOUNT PAYABLE\s*:?\s+Rs\s*([\d,.]+)")),
        }
        return json.dumps(fields)


def get_llm():
    """Factory: pick the provider based on configuration.

    Real key in the environment → real Claude. Otherwise → mock,
    so development never blocks on a key or a network.
    """
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        return AnthropicProvider(anthropic_key)
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        return GeminiProvider(gemini_key)
    return MockProvider()

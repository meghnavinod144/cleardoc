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

        fields = {
            "document_kind": "electricity_bill" if "Electricity" in text else "unknown",
            "consumer_number": find(r"Consumer Number\s*\n?\s*(\d+)"),
            "billing_period": find(r"Billing Period\s+(.+)"),
            "due_date": find(r"Due Date\s+(.+)"),
            "units_consumed_kwh": number(find(r"Units Consumed\s+([\d,]+)")),
            "total_amount_rs": number(find(r"TOTAL AMOUNT PAYABLE\s+Rs\s*([\d,.]+)")),
        }
        return json.dumps(fields)


def get_llm():
    """Factory: pick the provider based on configuration.

    Real key in the environment → real Claude. Otherwise → mock,
    so development never blocks on a key or a network.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return AnthropicProvider(api_key)
    return MockProvider()

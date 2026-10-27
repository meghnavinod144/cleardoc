"""Extraction: turn the OCR text blob into labeled, VALIDATED fields.

Two-layer defence:
  1. The prompt tells the LLM exactly what JSON shape to produce.
  2. Pydantic then VALIDATES what came back — because an LLM's output is
     never trusted blindly. If the LLM returns garbage, we fail loudly
     instead of storing nonsense. (Never trust input — now including
     the AI's own output. Same rule as uploads.)
"""

import json

from pydantic import BaseModel, ValidationError

from app.llm import get_llm


class BillFields(BaseModel):
    """The contract: extraction output MUST fit this shape.

    Every field is optional (None) — a torn or partial bill is normal,
    and an honest None beats an invented value. The types are enforced:
    if the LLM puts text where a number belongs, validation fails.
    """

    document_kind: str = "unknown"
    consumer_number: str | None = None
    billing_period: str | None = None
    due_date: str | None = None
    units_consumed_kwh: float | None = None
    total_amount_rs: float | None = None


EXTRACTION_PROMPT = """You are a precise data-extraction engine.
From the document text below, extract these fields as JSON:
- document_kind: "electricity_bill", "lab_report", or "unknown"
- consumer_number (string), billing_period, due_date
- units_consumed_kwh (number), total_amount_rs (number)

Rules: use null for anything not clearly present — NEVER guess or invent.
Output ONLY the JSON object, no explanations.

DOCUMENT TEXT:
{text}
"""


def extract_bill_fields(ocr_text: str) -> BillFields:
    """OCR text in → validated BillFields out."""
    llm = get_llm()
    raw_reply = llm.complete(EXTRACTION_PROMPT.format(text=ocr_text))

    # LLMs sometimes wrap JSON in ```json fences; strip them if present.
    cleaned = raw_reply.strip().removeprefix("```json").removesuffix("```").strip()

    try:
        data = json.loads(cleaned)          # is it even JSON?
        return BillFields(**data)           # does it fit the contract?
    except (json.JSONDecodeError, ValidationError) as error:
        # Fail loudly and traceably — never store garbage silently.
        raise ValueError(f"Extraction produced invalid output: {error}") from error

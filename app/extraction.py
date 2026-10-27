"""Extraction: classify the document, then extract its module's fields.

Now module-driven: this file no longer knows what a bill or a lab report
is. It asks the registry which module matches, builds the prompt from
that module's schema + instructions, and validates with that module's
contract. Adding document type #3 changes modules.py only.
"""

import json

from pydantic import BaseModel, ValidationError

from app.llm import get_llm
from app.modules import classify

EXTRACTION_PROMPT = """You are a precise data-extraction engine.
{instructions}

From the document text below, extract JSON with exactly these fields:
{field_list}

Rules: use null for anything not clearly present — NEVER guess or invent.
Output ONLY the JSON object, no explanations.

DOCUMENT TEXT:
{text}
"""


class GenericFields(BaseModel):
    """Fallback for unrecognized documents: no structured fields, but the
    document still flows on to indexing and Q&A — ANY readable document
    can be asked about; only the labeled-fields table needs a module."""


def extract_fields(ocr_text: str) -> tuple[str, BaseModel]:
    """OCR text in → (document kind, validated fields) out."""
    module = classify(ocr_text)
    if module is None:
        return "other", GenericFields()

    field_list = "\n".join(
        f"- {name}" for name in module.schema.model_fields
    )
    prompt = EXTRACTION_PROMPT.format(
        instructions=module.instructions,
        field_list=field_list,
        text=ocr_text,
    )

    raw_reply = get_llm().complete(prompt)
    cleaned = raw_reply.strip().removeprefix("```json").removesuffix("```").strip()

    try:
        data = json.loads(cleaned)           # is it even JSON?
        return module.kind, module.schema(**data)  # does it fit the contract?
    except (json.JSONDecodeError, ValidationError) as error:
        raise ValueError(f"Extraction produced invalid output: {error}") from error

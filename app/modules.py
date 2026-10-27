"""Document modules — the plug-in system.

THE architecture promise, now real: the core pipeline (upload → OCR →
extract → index → ask) knows nothing about bills or lab reports. Each
document type is a small class here declaring three things:
  - keywords:  how to recognize this document type
  - schema:    which labeled fields to extract (the Pydantic contract)
  - instructions: extra guidance for the LLM when extracting

Adding document type #3 (rental agreement, certificate…) = add ONE class
to this file and put it in REGISTRY. Nothing else in the project changes.
That sentence is the whole point of the design.
"""

from pydantic import BaseModel


# ---------------------------------------------------------------- bills --

class BillFields(BaseModel):
    """Extraction contract for utility bills. All optional:
    an honest None beats an invented value."""

    consumer_number: str | None = None
    billing_period: str | None = None
    due_date: str | None = None
    units_consumed_kwh: float | None = None
    total_amount_rs: float | None = None


class BillsModule:
    kind = "electricity_bill"
    keywords = ["electricity", "kwh", "tariff", "energy charge", "units consumed"]
    schema = BillFields
    instructions = (
        "This is a utility bill. Amounts are in rupees; strip commas from "
        "numbers. billing_period and due_date as printed on the bill."
    )


# ---------------------------------------------------------- lab reports --

class TestResult(BaseModel):
    """One test line on a lab report: name, measured value, unit,
    the lab's normal range, and the flag (LOW/HIGH/NORMAL) if printed."""

    name: str
    value: float | None = None
    unit: str | None = None
    reference_range: str | None = None
    flag: str | None = None


class LabReportFields(BaseModel):
    patient_name: str | None = None
    report_date: str | None = None
    lab_name: str | None = None
    tests: list[TestResult] = []


class LabReportsModule:
    kind = "lab_report"
    keywords = ["laboratory", "haemoglobin", "hemoglobin", "blood", "serum",
                "reference range", "test report", "pathology"]
    schema = LabReportFields
    instructions = (
        "This is a medical lab report. Extract every test row with its "
        "value, unit, reference range and flag. NEVER interpret or "
        "diagnose — extraction only. Copy flags exactly as printed."
    )


# ------------------------------------------------------------- registry --

REGISTRY = [BillsModule, LabReportsModule]


def classify(text: str):
    """Which module does this document belong to?

    v1: keyword scoring — count how many of each module's keywords appear.
    (Later: ask the LLM to classify, with this as the cheap first pass.)
    Returns the winning module, or None if nothing matches.
    """
    lowered = text.lower()
    best, best_score = None, 0
    for module in REGISTRY:
        score = sum(1 for kw in module.keywords if kw in lowered)
        if score > best_score:
            best, best_score = module, score
    return best

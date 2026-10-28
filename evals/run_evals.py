"""Eval runner: measure ClearDoc's answer quality against the golden set.

Run with:  python -m evals.run_evals

For every golden case it drives the REAL pipeline (in-process, via
TestClient — same as the test suite) and scores two things separately:

  RETRIEVAL score — did the right facts reach the retrieved excerpts?
      (Measures chunking + embeddings + search, independent of the LLM.)
  ANSWER score    — did the final answer contain the required facts?
      (Measures the whole system end to end.)

Scoring separately tells you WHERE a failure lives: retrieval bad →
fix chunking/embeddings; retrieval good but answer bad → fix the LLM
layer or prompt. One number per layer = debuggable quality.

Results are printed and saved to evals/results/ with a timestamp, so
improvements (like plugging in the real LLM) become measurable deltas.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

REFUSAL_MARKERS = ["cannot find", "not in the document", "does not contain",
                   "no information", "not mentioned", "can't find"]


def normalize(text: str) -> str:
    """Compare facts forgivingly: '3,014.90', 'Rs 3014.9' should match."""
    text = text.lower().replace(",", "")
    text = re.sub(r"\s+", " ", text)
    # strip trailing zeros in decimals so 3014.90 == 3014.9
    text = re.sub(r"(\d+\.\d*?)0+\b", r"\1", text)
    return text


def contains(haystack: str, fact: str) -> bool:
    return normalize(fact) in normalize(haystack)


def run() -> dict:
    client = TestClient(app)

    # One throwaway eval user per run.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    signup = client.post("/auth/signup", json={
        "email": f"eval-{stamp}@cleardoc.local", "password": "eval-pass-123"})
    headers = {"Authorization": f"Bearer {signup.json()['token']}"}

    cases = json.loads(Path("evals/golden_set.json").read_text())["cases"]

    # Process each unique document once through the pipeline.
    doc_ids: dict[str, str] = {}
    for path in {c["document"] for c in cases}:
        with open(path, "rb") as f:
            upload = client.post("/documents", headers=headers,
                                 files={"file": (Path(path).name, f, "image/png")})
        doc_id = upload.json()["document_id"]
        client.post(f"/documents/{doc_id}/ocr", headers=headers)
        client.post(f"/documents/{doc_id}/extract", headers=headers)
        client.post(f"/documents/{doc_id}/index", headers=headers)
        doc_ids[path] = doc_id

    results = []
    for case in cases:
        reply = client.post(
            f"/documents/{doc_ids[case['document']]}/ask", headers=headers,
            json={"question": case["question"]},
        ).json()
        answer = reply["answer"]
        sources_text = " ".join(s["text"] for s in reply["sources"])

        if case.get("must_refuse"):
            # Honesty case: pass = the answer admits the fact is absent.
            answer_pass = any(m in answer.lower() for m in REFUSAL_MARKERS)
            retrieval_pass = None  # not applicable
        else:
            retrieval_pass = all(contains(sources_text, f) for f in case["required_facts"])
            answer_pass = all(contains(answer, f) for f in case["required_facts"])

        results.append({
            "id": case["id"],
            "retrieval_pass": retrieval_pass,
            "answer_pass": answer_pass,
            "answer_preview": answer[:110],
        })

    scored = [r for r in results if r["retrieval_pass"] is not None]
    summary = {
        "timestamp": stamp,
        "provider": "mock" if "MockProvider" in answer else "real",
        "retrieval_score": f"{sum(r['retrieval_pass'] for r in scored)}/{len(scored)}",
        "answer_score": f"{sum(r['answer_pass'] for r in results)}/{len(results)}",
        "cases": results,
    }

    out_dir = Path("evals/results")
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"run_{stamp}.json").write_text(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    s = run()
    print(f"\n=== ClearDoc evals ({s['provider']} provider) ===")
    print(f"retrieval: {s['retrieval_score']}    answers: {s['answer_score']}\n")
    for r in s["cases"]:
        retr = {True: "✓", False: "✗", None: "–"}[r["retrieval_pass"]]
        answ = "✓" if r["answer_pass"] else "✗"
        print(f"  retrieval {retr}  answer {answ}   {r['id']}")
    print()
    sys.exit(0)

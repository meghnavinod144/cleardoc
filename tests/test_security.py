"""Security tests — a robot that PROVES the promises every run.

Run with:  pytest
Each test spins up the app in-process (TestClient — no real server
needed), performs real HTTP calls, and asserts on the responses. When
CI/CD arrives, these run automatically on every push: a change that
breaks isolation can never reach production unnoticed.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def make_user(email: str) -> dict:
    """Sign a user up and return auth headers for them."""
    response = client.post("/auth/signup", json={"email": email, "password": "test-pass-123"})
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['token']}"}


def upload_bill(headers: dict) -> str:
    with open("data/sample_bill.png", "rb") as f:
        response = client.post("/documents", headers=headers,
                               files={"file": ("bill.png", f, "image/png")})
    assert response.status_code == 201
    return response.json()["document_id"]


def test_no_token_means_401():
    """Every document endpoint refuses anonymous callers."""
    assert client.get("/documents").status_code == 401
    assert client.post("/documents").status_code == 401


def test_wrong_password_rejected():
    make_user("wrongpass@test.in")
    response = client.post("/auth/login",
                           json={"email": "wrongpass@test.in", "password": "not-the-password"})
    assert response.status_code == 401


def test_short_password_rejected():
    response = client.post("/auth/signup", json={"email": "short@test.in", "password": "abc"})
    assert response.status_code == 422


def test_user_isolation():
    """THE test: user B must never see user A's document — and the
    response must be indistinguishable from 'no such document'."""
    headers_a = make_user("usera@test.in")
    headers_b = make_user("userb@test.in")
    doc_id = upload_bill(headers_a)

    assert client.get(f"/documents/{doc_id}", headers=headers_a).status_code == 200
    assert client.get(f"/documents/{doc_id}", headers=headers_b).status_code == 404
    assert client.post(f"/documents/{doc_id}/ocr", headers=headers_b).status_code == 404

    # B's document list must not contain A's document.
    listing = client.get("/documents", headers=headers_b).json()
    assert all(d["document_id"] != doc_id for d in listing)


def test_upload_rejects_wrong_type():
    headers = make_user("types@test.in")
    response = client.post("/documents", headers=headers,
                           files={"file": ("evil.exe", b"bad", "application/x-msdownload")})
    assert response.status_code == 415


def test_original_file_deleted_after_indexing(tmp_path):
    """The privacy promise: after indexing, the uploaded file is gone."""
    from pathlib import Path

    headers = make_user("privacy@test.in")
    doc_id = upload_bill(headers)
    client.post(f"/documents/{doc_id}/ocr", headers=headers)
    client.post(f"/documents/{doc_id}/extract", headers=headers)
    client.post(f"/documents/{doc_id}/index", headers=headers)

    stored = list(Path("data/uploads").glob(f"{doc_id}*"))
    assert stored == [], "original file should be deleted after indexing"

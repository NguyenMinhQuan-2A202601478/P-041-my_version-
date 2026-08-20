"""Tests for /api/v1/cvs/* (F-02: Upload & Parse CV).

NOTE on mocking `parse_cv`: `src/api/v1/cvs.py::upload_cv` awaits
`parse_cv(content, file.filename)` and reads `raw_text` / `parsed_json` off
the dict it returns, matching the real `src.services.cv_parser.parse_cv`
(`async def` returning `{"raw_text": ..., "parsed_json": ...}`). Tests that
need a successful upload monkeypatch `src.api.v1.cvs.parse_cv` with an async
fake returning that same dict, so routing / validation / ownership behavior
can be verified without calling the LLM.
"""

from __future__ import annotations

import pytest

UPLOAD_URL = "/api/v1/cvs/upload"


async def _fake_parse_cv(content: bytes, filename: str) -> dict:
    return {
        "raw_text": "Nguyen Van A - Backend Developer. Ky nang: Python, FastAPI, PostgreSQL.",
        "parsed_json": {"full_name": "Nguyen Van A", "skills": ["Python", "FastAPI", "PostgreSQL"]},
    }


@pytest.fixture(autouse=True)
def _patch_parse_cv(monkeypatch):
    monkeypatch.setattr("src.api.v1.cvs.parse_cv", _fake_parse_cv)


def test_upload_valid_pdf_returns_201(student_client):
    files = {"file": ("resume.pdf", b"%PDF-1.4 fake pdf bytes for testing", "application/pdf")}
    response = student_client.post(UPLOAD_URL, files=files, data={"title": "CV Backend"})

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "CV Backend"
    assert body["status"] == "draft"
    assert body["parsed_json"]["full_name"] == "Nguyen Van A"


def test_upload_valid_docx_returns_201(student_client):
    files = {
        "file": (
            "resume.docx",
            b"PK\x03\x04 fake docx bytes for testing",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    response = student_client.post(UPLOAD_URL, files=files, data={"title": "CV Backend"})
    assert response.status_code == 201


def test_upload_invalid_file_type_returns_400(student_client):
    files = {"file": ("resume.txt", b"plain text resume", "text/plain")}
    response = student_client.post(UPLOAD_URL, files=files, data={"title": "CV Backend"})

    assert response.status_code == 400


def test_upload_oversized_file_returns_400(student_client):
    from src.config import settings

    oversized = b"0" * (settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024 + 1)
    files = {"file": ("resume.pdf", oversized, "application/pdf")}
    response = student_client.post(UPLOAD_URL, files=files, data={"title": "CV Backend"})

    assert response.status_code == 400


def test_upload_empty_file_returns_400(student_client):
    files = {"file": ("resume.pdf", b"", "application/pdf")}
    response = student_client.post(UPLOAD_URL, files=files, data={"title": "CV Backend"})

    assert response.status_code == 400


def test_upload_requires_auth(client):
    files = {"file": ("resume.pdf", b"%PDF-1.4 bytes", "application/pdf")}
    response = client.post(UPLOAD_URL, files=files, data={"title": "CV Backend"})
    assert response.status_code == 401


def test_list_cvs_returns_only_current_users_cvs(student_client, other_student_client, make_cv):
    make_cv(student_client, title="CV cua A")
    make_cv(other_student_client, title="CV cua B")

    response = student_client.get("/api/v1/cvs/")

    assert response.status_code == 200
    titles = [item["title"] for item in response.json()]
    assert titles == ["CV cua A"]


def test_get_cv_detail_returns_correct_data(student_client, make_cv):
    cv = make_cv(student_client, title="CV Fullstack")

    response = student_client.get(f"/api/v1/cvs/{cv.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == cv.id
    assert body["title"] == "CV Fullstack"


def test_get_cv_not_found_returns_404(student_client):
    response = student_client.get("/api/v1/cvs/does-not-exist")
    assert response.status_code == 404


def test_delete_cv_then_get_returns_404(student_client, make_cv):
    cv = make_cv(student_client)

    delete_response = student_client.delete(f"/api/v1/cvs/{cv.id}")
    assert delete_response.status_code == 200

    get_response = student_client.get(f"/api/v1/cvs/{cv.id}")
    assert get_response.status_code == 404


def test_confirm_cv_updates_status(student_client, make_cv):
    cv = make_cv(student_client, status="draft")

    response = student_client.put(f"/api/v1/cvs/{cv.id}/confirm")

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_student_cannot_access_other_students_cv(student_client, other_student_client, make_cv):
    cv = make_cv(other_student_client, title="CV rieng tu cua B")

    response = student_client.get(f"/api/v1/cvs/{cv.id}")

    assert response.status_code == 403


def test_student_cannot_delete_other_students_cv(student_client, other_student_client, make_cv):
    cv = make_cv(other_student_client)

    response = student_client.delete(f"/api/v1/cvs/{cv.id}")

    assert response.status_code == 403


def test_admin_can_access_any_students_cv(admin_client, student_client, make_cv):
    cv = make_cv(student_client, title="CV cua sinh vien")

    response = admin_client.get(f"/api/v1/cvs/{cv.id}")

    assert response.status_code == 200

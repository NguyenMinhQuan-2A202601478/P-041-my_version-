"""Tests for /api/v1/jds/* (F-03: thu vien JD + dan JD ngoai)."""

from __future__ import annotations

PASTE_URL = "/api/v1/jds/paste"
LIST_URL = "/api/v1/jds/"


def _paste_payload(**overrides) -> dict:
    payload = {
        "title": "Backend Developer (Fresher)",
        "company": "Cong ty XYZ (du lieu gia lap)",
        "location": "Ha Noi",
        "requirements_text": "Yeu cau: Python, FastAPI, PostgreSQL, Git.",
    }
    payload.update(overrides)
    return payload


def test_paste_jd_with_valid_data_returns_201(student_client):
    response = student_client.post(PASTE_URL, json=_paste_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Backend Developer (Fresher)"
    assert body["is_system"] is False
    assert "id" in body


def test_paste_jd_requires_auth(client):
    response = client.post(PASTE_URL, json=_paste_payload())
    assert response.status_code == 401


def test_paste_jd_rejects_empty_title(student_client):
    response = student_client.post(PASTE_URL, json=_paste_payload(title=""))
    assert response.status_code == 422


def test_paste_jd_rejects_empty_requirements(student_client):
    response = student_client.post(PASTE_URL, json=_paste_payload(requirements_text=""))
    assert response.status_code == 422


def test_list_jds_includes_pasted_jd(student_client):
    student_client.post(PASTE_URL, json=_paste_payload(title="Data Analyst Intern"))

    response = student_client.get(LIST_URL)

    assert response.status_code == 200
    titles = [item["title"] for item in response.json()]
    assert "Data Analyst Intern" in titles


def test_get_jd_detail_returns_correct_data(student_client):
    created = student_client.post(PASTE_URL, json=_paste_payload(title="QA Engineer")).json()

    response = student_client.get(f"/api/v1/jds/{created['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "QA Engineer"
    assert body["requirements_text"] == "Yeu cau: Python, FastAPI, PostgreSQL, Git."


def test_get_jd_not_found_returns_404(student_client):
    response = student_client.get("/api/v1/jds/does-not-exist")
    assert response.status_code == 404


def test_list_jds_search_filters_by_title(student_client):
    student_client.post(PASTE_URL, json=_paste_payload(title="Backend Developer"))
    student_client.post(PASTE_URL, json=_paste_payload(title="Frontend Developer"))

    response = student_client.get(LIST_URL, params={"search": "Backend"})

    assert response.status_code == 200
    titles = [item["title"] for item in response.json()]
    assert titles == ["Backend Developer"]

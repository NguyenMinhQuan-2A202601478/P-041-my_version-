"""Tests for /api/v1/analysis/* (F-03, F-04: Gap Analysis + HITL Accept/Reject).

The real Gap Analysis Agent is a LangGraph pipeline that calls an LLM (see
src/agents/gap_analysis/). Per the QA task's constraints, these API tests
mock the service layer boundary instead of hitting a real LLM: they patch
`src.api.v1.analysis.run_gap_analysis`, the exact name the route imports
(see the module docstring in src/api/v1/analysis.py — the real service file
is `gap_analysis_service.py` exposing `analyze_cv_against_jd`, a different
name in a different module, so the route's own `try/except ImportError`
already falls back to `run_gap_analysis = None` today; this integration gap
is reported separately in the QA findings, not fixed here since src/ is out
of scope for this agent).
"""

from __future__ import annotations

import pytest

GAP_URL = "/api/v1/analysis/gap"
HISTORY_URL = "/api/v1/analysis/history"


def _fake_result(**overrides) -> dict:
    result = {
        "match_score": 72.5,
        "gap_analysis": {
            "matched_skills": ["Python", "FastAPI"],
            "missing_skills": ["Docker"],
        },
        "suggestions": [
            {
                "section": "experience",
                "original_text": "Xay dung API cho he thong quan ly",
                "suggested_text": "Thiet ke va xay dung RESTful API cho he thong quan ly noi bo",
                "reason": "Bo sung Action Verb",
            },
            {
                "section": "experience",
                "original_text": "Ho tro van hanh he thong",
                "suggested_text": "Van hanh va giam sat he thong noi bo hang ngay",
                "reason": "Lam ro trach nhiem",
            },
        ],
    }
    result.update(overrides)
    return result


@pytest.fixture(autouse=True)
def _patch_run_gap_analysis(monkeypatch):
    def _fake_run_gap_analysis(cv, jd):
        return _fake_result()

    monkeypatch.setattr("src.api.v1.analysis.run_gap_analysis", _fake_run_gap_analysis)


def test_start_gap_analysis_valid_returns_200(student_client, make_cv, make_jd):
    cv = make_cv(student_client)
    jd = make_jd()

    response = student_client.post(GAP_URL, json={"cv_id": cv.id, "jd_id": jd.id})

    assert response.status_code == 201
    body = response.json()
    assert body["match_score"] == 72.5
    assert body["cv_id"] == cv.id
    assert body["jd_id"] == jd.id
    assert len(body["suggestions"]) == 2


def test_start_gap_analysis_invalid_cv_id_returns_404(student_client, make_jd):
    jd = make_jd()

    response = student_client.post(GAP_URL, json={"cv_id": "does-not-exist", "jd_id": jd.id})

    assert response.status_code == 404


def test_start_gap_analysis_invalid_jd_id_returns_404(student_client, make_cv):
    cv = make_cv(student_client)

    response = student_client.post(GAP_URL, json={"cv_id": cv.id, "jd_id": "does-not-exist"})

    assert response.status_code == 404


def test_start_gap_analysis_on_other_students_cv_returns_404(student_client, other_student_client, make_cv, make_jd):
    """The route looks up the CV filtered by the caller's user_id, so a CV
    owned by someone else is indistinguishable from a nonexistent one."""
    other_cv = make_cv(other_student_client)
    jd = make_jd()

    response = student_client.post(GAP_URL, json={"cv_id": other_cv.id, "jd_id": jd.id})

    assert response.status_code == 404


def test_accept_suggestion_records_decision(student_client, make_cv, make_jd):
    cv = make_cv(student_client)
    jd = make_jd()
    analysis_id = student_client.post(GAP_URL, json={"cv_id": cv.id, "jd_id": jd.id}).json()["id"]

    response = student_client.post(
        f"/api/v1/analysis/{analysis_id}/decide",
        json={"suggestion_index": 0, "accepted": True, "final_text": "Da chinh sua theo goi y"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["suggestion_index"] == 0
    assert body["final_text"] == "Da chinh sua theo goi y"


def test_reject_suggestion_records_decision(student_client, make_cv, make_jd):
    cv = make_cv(student_client)
    jd = make_jd()
    analysis_id = student_client.post(GAP_URL, json={"cv_id": cv.id, "jd_id": jd.id}).json()["id"]

    response = student_client.post(
        f"/api/v1/analysis/{analysis_id}/decide",
        json={"suggestion_index": 1, "accepted": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is False


def test_get_analysis_history_returns_only_current_users_analyses(
    student_client, other_student_client, make_cv, make_jd
):
    cv_a = make_cv(student_client)
    cv_b = make_cv(other_student_client)
    jd = make_jd()
    student_client.post(GAP_URL, json={"cv_id": cv_a.id, "jd_id": jd.id})
    other_student_client.post(GAP_URL, json={"cv_id": cv_b.id, "jd_id": jd.id})

    response = student_client.get(HISTORY_URL)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["cv_id"] == cv_a.id


def test_get_analysis_detail_matches_created_analysis(student_client, make_cv, make_jd):
    cv = make_cv(student_client)
    jd = make_jd()
    created = student_client.post(GAP_URL, json={"cv_id": cv.id, "jd_id": jd.id}).json()

    response = student_client.get(f"/api/v1/analysis/{created['id']}")

    assert response.status_code == 200
    assert response.json()["match_score"] == 72.5


def test_cross_user_cannot_view_others_analysis(student_client, other_student_client, make_cv, make_jd):
    cv = make_cv(student_client)
    jd = make_jd()
    analysis_id = student_client.post(GAP_URL, json={"cv_id": cv.id, "jd_id": jd.id}).json()["id"]

    response = other_student_client.get(f"/api/v1/analysis/{analysis_id}")

    assert response.status_code == 403

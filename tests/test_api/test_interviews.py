"""Tests for /api/v1/interviews/* (F-05, F-06: Mock Interview + STAR report).

Mocks the service boundary the route actually imports from
`src/services/interview_service.py` -- `generate_questions_for_session`,
`evaluate_single_answer` and `generate_report_for_session` -- instead of
calling a real LLM. All three are `async` with keyword-only parameters, and
the fakes below mirror those signatures plus the result shapes the route
reads.

`generate_report_for_session` is faked too because completing the last
question triggers `_create_report()`, which would otherwise reach for a real
LLM; with the fake, the `interview_reports` row is written the same way it
is in production. Tests for `GET /interviews/{id}/report` still insert their
own `InterviewReport` row via `db_session` so they exercise the endpoint's
read/serialization logic against known values.
"""

from __future__ import annotations

import pytest

START_URL = "/api/v1/interviews/start"


async def _fake_generate_questions_for_session(
    *,
    cv_text: str,
    cv_parsed_json: dict | None = None,
    jd_title: str,
    jd_requirements: str,
    num_questions: int = 5,
) -> list[str]:
    return [f"Cau hoi phong van so {i + 1} cho vi tri {jd_title}" for i in range(num_questions)]


async def _fake_evaluate_single_answer(*, question_text: str, user_answer: str) -> dict:
    return {
        "needs_follow_up": False,
        "follow_up_question": None,
        "star_score": {"situation": 20.0, "task": 20.0, "action": 20.0, "result": 20.0},
        "feedback": "Cau tra loi day du theo STAR",
    }


async def _fake_generate_report_for_session(*, qa_history: list[dict], jd_title: str) -> dict:
    return {
        "total_score": 80.0,
        "star_scores": {
            "situation": {"score": 20.0, "max": 25, "feedback": "Ro rang"},
            "task": {"score": 20.0, "max": 25, "feedback": "Cu the"},
            "action": {"score": 20.0, "max": 25, "feedback": "Chi tiet"},
            "result": {"score": 20.0, "max": 25, "feedback": "Co so lieu"},
        },
        "strengths": ["Trinh bay mach lac"],
        "improvements": ["Bo sung so lieu ket qua"],
        "recommendations": [],
    }


@pytest.fixture(autouse=True)
def _patch_interview_service(monkeypatch):
    monkeypatch.setattr("src.api.v1.interviews.generate_questions_for_session", _fake_generate_questions_for_session)
    monkeypatch.setattr("src.api.v1.interviews.evaluate_single_answer", _fake_evaluate_single_answer)
    monkeypatch.setattr("src.api.v1.interviews.generate_report_for_session", _fake_generate_report_for_session)


def test_start_interview_with_valid_cv_and_jd_returns_201(student_client, make_cv, make_jd):
    cv = make_cv(student_client)
    jd = make_jd()

    response = student_client.post(START_URL, json={"cv_id": cv.id, "jd_id": jd.id, "total_questions": 5})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ongoing"
    assert body["total_questions"] == 5
    assert body["current_index"] == 0
    assert body["first_question"]["index"] == 0


def test_start_interview_missing_cv_and_jd_returns_422(student_client):
    response = student_client.post(START_URL, json={})
    assert response.status_code == 422


def test_start_interview_nonexistent_cv_returns_404(student_client, make_jd):
    jd = make_jd()
    response = student_client.post(START_URL, json={"cv_id": "no-such-cv", "jd_id": jd.id})
    assert response.status_code == 404


def test_start_interview_nonexistent_jd_returns_404(student_client, make_cv):
    cv = make_cv(student_client)
    response = student_client.post(START_URL, json={"cv_id": cv.id, "jd_id": "no-such-jd"})
    assert response.status_code == 404


def test_start_interview_total_questions_out_of_range_returns_422(student_client, make_cv, make_jd):
    cv = make_cv(student_client)
    jd = make_jd()
    response = student_client.post(START_URL, json={"cv_id": cv.id, "jd_id": jd.id, "total_questions": 9})
    assert response.status_code == 422


def test_submit_response_returns_evaluation_and_advances(student_client, make_cv, make_jd):
    cv = make_cv(student_client)
    jd = make_jd()
    session_id = student_client.post(START_URL, json={"cv_id": cv.id, "jd_id": jd.id, "total_questions": 5}).json()[
        "session_id"
    ]

    response = student_client.post(f"/api/v1/interviews/{session_id}/respond", json={"answer": "Cau tra loi cua toi"})

    assert response.status_code == 200
    body = response.json()
    assert body["current_index"] == 1
    assert body["is_follow_up"] is False
    assert body["status"] == "ongoing"
    assert body["next_question"]["index"] == 1


def test_submit_response_completes_session_after_last_question(student_client, make_cv, make_jd):
    cv = make_cv(student_client)
    jd = make_jd()
    session_id = student_client.post(START_URL, json={"cv_id": cv.id, "jd_id": jd.id, "total_questions": 5}).json()[
        "session_id"
    ]

    last_response = None
    for _ in range(5):
        last_response = student_client.post(f"/api/v1/interviews/{session_id}/respond", json={"answer": "Cau tra loi"})

    assert last_response.status_code == 200
    body = last_response.json()
    assert body["status"] == "completed"
    assert body["next_question"] is None


def test_submit_response_with_follow_up_needed(student_client, make_cv, make_jd, monkeypatch):
    async def _fake_needs_follow_up(*, question_text: str, user_answer: str) -> dict:
        return {
            "needs_follow_up": True,
            "follow_up_question": "Ban co the neu cu the ket qua dat duoc khong?",
            "star_score": {"situation": 10.0, "task": 10.0, "action": 10.0, "result": 5.0},
        }

    monkeypatch.setattr("src.api.v1.interviews.evaluate_single_answer", _fake_needs_follow_up)
    cv = make_cv(student_client)
    jd = make_jd()
    session_id = student_client.post(START_URL, json={"cv_id": cv.id, "jd_id": jd.id, "total_questions": 5}).json()[
        "session_id"
    ]

    response = student_client.post(f"/api/v1/interviews/{session_id}/respond", json={"answer": "OK"})

    assert response.status_code == 200
    body = response.json()
    assert body["is_follow_up"] is True
    assert body["next_question"]["text"] == "Ban co the neu cu the ket qua dat duoc khong?"


def test_submit_response_requires_auth(client):
    response = client.post("/api/v1/interviews/some-session/respond", json={"answer": "hi"})
    assert response.status_code == 401


def test_submit_response_to_others_session_returns_403(student_client, other_student_client, make_cv, make_jd):
    cv = make_cv(other_student_client)
    jd = make_jd()
    session_id = other_student_client.post(
        START_URL, json={"cv_id": cv.id, "jd_id": jd.id, "total_questions": 5}
    ).json()["session_id"]

    response = student_client.post(f"/api/v1/interviews/{session_id}/respond", json={"answer": "hi"})

    assert response.status_code == 403


def test_get_report_returns_star_scores(student_client, make_cv, make_jd, db_session):
    from src.db.models import InterviewReport, InterviewSession

    cv = make_cv(student_client)
    jd = make_jd()
    session_id = student_client.post(START_URL, json={"cv_id": cv.id, "jd_id": jd.id, "total_questions": 5}).json()[
        "session_id"
    ]
    session = db_session.get(InterviewSession, session_id)
    session.status = "completed"
    report = InterviewReport(
        session_id=session_id,
        total_score=75.5,
        star_scores_json={
            "situation": {"score": 18.5, "max": 25, "feedback": "Ro rang"},
            "task": {"score": 20.0, "max": 25, "feedback": "Cu the"},
            "action": {"score": 22.0, "max": 25, "feedback": "Chi tiet"},
            "result": {"score": 15.0, "max": 25, "feedback": "Can bo sung so lieu"},
        },
        strengths_json=["Trinh bay logic ro rang"],
        improvements_json=["Can mo ta ket qua cu the hon"],
        recommendations_json=[{"question_index": 0, "sample_answer": "Vi du toi uu hoa truy van SQL..."}],
    )
    db_session.add(report)
    db_session.commit()

    response = student_client.get(f"/api/v1/interviews/{session_id}/report")

    assert response.status_code == 200
    body = response.json()
    assert body["total_score"] == 75.5
    assert body["star_scores"]["situation"]["score"] == 18.5
    assert body["strengths"] == ["Trinh bay logic ro rang"]


def test_get_report_before_ready_returns_404(student_client, make_cv, make_jd):
    cv = make_cv(student_client)
    jd = make_jd()
    session_id = student_client.post(START_URL, json={"cv_id": cv.id, "jd_id": jd.id, "total_questions": 5}).json()[
        "session_id"
    ]

    response = student_client.get(f"/api/v1/interviews/{session_id}/report")

    assert response.status_code == 404


def test_get_interview_history_returns_only_current_users_sessions(
    student_client, other_student_client, make_cv, make_jd
):
    cv_a = make_cv(student_client)
    cv_b = make_cv(other_student_client)
    jd = make_jd()
    student_client.post(START_URL, json={"cv_id": cv_a.id, "jd_id": jd.id, "total_questions": 5})
    other_student_client.post(START_URL, json={"cv_id": cv_b.id, "jd_id": jd.id, "total_questions": 5})

    response = student_client.get("/api/v1/interviews/history")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_interview_status(student_client, make_cv, make_jd):
    cv = make_cv(student_client)
    jd = make_jd()
    session_id = student_client.post(START_URL, json={"cv_id": cv.id, "jd_id": jd.id, "total_questions": 5}).json()[
        "session_id"
    ]

    response = student_client.get(f"/api/v1/interviews/{session_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["status"] == "ongoing"

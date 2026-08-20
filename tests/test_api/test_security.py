"""Cross-cutting security tests: role isolation, data ownership, and token
handling that apply across multiple routers (see CLAUDE.md constraints 3 and
4 — "Phan quyen" and "Bao mat"). Endpoint-specific happy-path behavior is
covered in the per-router test files; this file focuses on what should be
REJECTED.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

# ---------------------------------------------------------------------------
# Cross-role access
# ---------------------------------------------------------------------------


def test_student_accessing_counselor_only_endpoint_returns_403(student_client):
    response = student_client.get("/api/v1/counselor/dashboard")
    assert response.status_code == 403


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/counselor/students"),
        ("GET", "/api/v1/counselor/dashboard"),
    ],
)
def test_student_blocked_from_every_counselor_route(student_client, method, path):
    response = student_client.request(method, path)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Cross-user access (data ownership)
# ---------------------------------------------------------------------------


def test_student_a_cannot_read_student_bs_cv(student_client, other_student_client, make_cv):
    cv = make_cv(other_student_client)
    response = student_client.get(f"/api/v1/cvs/{cv.id}")
    assert response.status_code == 403


def test_student_a_cannot_delete_student_bs_cv(student_client, other_student_client, make_cv):
    cv = make_cv(other_student_client)
    response = student_client.delete(f"/api/v1/cvs/{cv.id}")
    assert response.status_code == 403


def test_student_a_cannot_confirm_student_bs_cv(student_client, other_student_client, make_cv):
    cv = make_cv(other_student_client, status="draft")
    response = student_client.put(f"/api/v1/cvs/{cv.id}/confirm")
    assert response.status_code == 403


def test_counselor_without_grant_cannot_read_student_reports(counselor_client, student_client):
    response = counselor_client.get(f"/api/v1/counselor/students/{student_client.current_user.id}/reports")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# JWT handling
# ---------------------------------------------------------------------------


def test_missing_authorization_header_returns_401(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_malformed_bearer_token_returns_401(client):
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer this.is.not.a.jwt"})
    assert response.status_code == 401


def test_token_signed_with_wrong_secret_returns_401(client, student_client):
    from jose import jwt as jose_jwt

    from src.config import settings

    bad_token = jose_jwt.encode(
        {"sub": student_client.current_user.id, "role": "admin"},
        "a-completely-different-secret",
        algorithm=settings.JWT_ALGORITHM,
    )
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bad_token}"})
    assert response.status_code == 401


def test_expired_token_returns_401(client, student_client):
    from src.core.security import create_access_token

    expired_token = create_access_token(
        data={"sub": student_client.current_user.id, "role": "student"},
        expires_delta=timedelta(minutes=-5),
    )
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert response.status_code == 401


def test_token_for_deleted_user_returns_401(client, db_session, make_client):
    ghost_client = make_client(role="student")
    token = ghost_client.headers["Authorization"]

    from src.db.models import User

    db_session.delete(db_session.get(User, ghost_client.current_user.id))
    db_session.commit()

    response = client.get("/api/v1/auth/me", headers={"Authorization": token})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Injection safety — SQLAlchemy's ORM parameterizes queries, so raw SQL
# injection strings should just be treated as inert data, not executed.
# ---------------------------------------------------------------------------


def test_sql_injection_payload_in_register_fields_is_stored_inertly(client, db_session):
    from src.db.models import User

    payload = {
        "email": "injection.test@example.test",
        "password": "Sup3r-Secret-1",
        "full_name": "Robert'); DROP TABLE users;--",
        "role": "student",
    }

    response = client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 201
    assert response.json()["full_name"] == "Robert'); DROP TABLE users;--"
    # The users table must still exist and be queryable — a real injection
    # would have dropped it.
    assert db_session.query(User).count() >= 1


def test_sql_injection_payload_in_jd_search_does_not_error(student_client):
    response = student_client.get("/api/v1/jds/", params={"search": "' OR '1'='1"})

    assert response.status_code == 200
    assert response.json() == []


def test_sql_injection_payload_in_jd_paste_is_stored_inertly(student_client):
    response = student_client.post(
        "/api/v1/jds/paste",
        json={
            "title": "'; DROP TABLE job_descriptions;--",
            "requirements_text": "Yeu cau: Python",
        },
    )

    assert response.status_code == 201

    # If the injection had executed, this second call would error instead
    # of returning a normal list.
    list_response = student_client.get("/api/v1/jds/")
    assert list_response.status_code == 200

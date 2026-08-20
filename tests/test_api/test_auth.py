"""Tests for /api/v1/auth/* (F-01: dang nhap va phan quyen)."""

from __future__ import annotations

from jose import jwt

from src.config import settings

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"


def _register_payload(**overrides) -> dict:
    payload = {
        "email": "sinhvien.test@example.test",
        "password": "Sup3r-Secret-1",
        "full_name": "Nguyen Van A",
        "role": "student",
    }
    payload.update(overrides)
    return payload


def test_register_with_valid_data_creates_user(client):
    response = client.post(REGISTER_URL, json=_register_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "sinhvien.test@example.test"
    assert body["full_name"] == "Nguyen Van A"
    assert body["role"] == "student"
    assert "id" in body
    # Password must never be echoed back.
    assert "password" not in body
    assert "hashed_password" not in body


def test_register_with_duplicate_email_returns_error(client):
    client.post(REGISTER_URL, json=_register_payload())

    response = client.post(REGISTER_URL, json=_register_payload(full_name="Nguyen Van B"))

    assert response.status_code == 409
    assert "detail" in response.json()


def test_register_rejects_invalid_email_format(client):
    response = client.post(REGISTER_URL, json=_register_payload(email="not-an-email"))
    assert response.status_code == 422


def test_register_rejects_short_password(client):
    response = client.post(REGISTER_URL, json=_register_payload(password="short"))
    assert response.status_code == 422


def test_register_unknown_role_falls_back_to_student(client):
    response = client.post(REGISTER_URL, json=_register_payload(role="superadmin"))
    assert response.status_code == 201
    assert response.json()["role"] == "student"


def test_login_with_correct_credentials_returns_token(client):
    client.post(REGISTER_URL, json=_register_payload())

    response = client.post(LOGIN_URL, json={"email": "sinhvien.test@example.test", "password": "Sup3r-Secret-1"})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "sinhvien.test@example.test"


def test_login_with_wrong_password_returns_401(client):
    client.post(REGISTER_URL, json=_register_payload())

    response = client.post(LOGIN_URL, json={"email": "sinhvien.test@example.test", "password": "wrong-password"})

    assert response.status_code == 401


def test_login_with_unknown_email_returns_401(client):
    response = client.post(LOGIN_URL, json={"email": "nobody@example.test", "password": "whatever123"})
    assert response.status_code == 401


def test_me_with_valid_token_returns_user_info(client):
    client.post(REGISTER_URL, json=_register_payload())
    login = client.post(LOGIN_URL, json={"email": "sinhvien.test@example.test", "password": "Sup3r-Secret-1"})
    token = login.json()["access_token"]

    response = client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == "sinhvien.test@example.test"


def test_me_without_token_returns_401(client):
    response = client.get(ME_URL)
    assert response.status_code == 401


def test_me_with_garbage_token_returns_401(client):
    response = client.get(ME_URL, headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_registered_role_matches_token_role_claim(client):
    client.post(REGISTER_URL, json=_register_payload(role="counselor"))
    login = client.post(LOGIN_URL, json={"email": "sinhvien.test@example.test", "password": "Sup3r-Secret-1"})
    token = login.json()["access_token"]

    # Decode the JWT payload directly to confirm the `role` claim was set
    # from the registered role (not silently defaulted).
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    assert payload["role"] == "counselor"

    me_response = client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    assert me_response.json()["role"] == "counselor"


def test_google_oauth_is_not_yet_implemented(client):
    """Documents current behavior: the endpoint exists per the API contract
    but intentionally refuses to trust an unverified Google token (see
    src/api/v1/auth.py docstring) until GOOGLE_CLIENT_ID/SECRET are wired."""
    response = client.post("/api/v1/auth/google", json={"google_token": "fake-token"})
    assert response.status_code == 501

"""Shared pytest fixtures for CV Assistant tests.

All test data here is synthetic — no real personal information — per the
project rule in CLAUDE.md: "Du lieu test luon synthetic (CV/JD gia lap)".

Design notes for future maintainers:
- Every test gets its own fresh in-memory SQLite database (function-scoped
  `db_engine`), so tests never share state and never touch a real dev.db /
  production database.
- `app_with_test_db` overrides FastAPI's `get_db` dependency to hand out
  sessions bound to that same in-memory engine, so requests made through the
  `client`/`*_client` fixtures see exactly the rows the test set up via
  `db_session` (or the `make_*` helper fixtures below).
- `make_client(role=...)` is the one factory every authenticated-fixture in
  this file is built from: it creates a User row directly (bypassing
  /auth/register, which keeps these fixtures fast and independent of the
  auth endpoints under test) and returns a `TestClient` with a valid JWT
  already set in its default headers.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_engine():
    """Fresh in-memory SQLite engine, one per test.

    `StaticPool` is required for SQLite ``:memory:`` databases used from
    multiple `Session` objects (as this test suite does): without it, every
    checkout from the pool would open a *new* empty in-memory database
    instead of sharing the one this fixture just created the schema in.
    """
    # Import models so every table is registered on `Base.metadata` before
    # `create_all` runs (mirrors `create_tables()` in src/db/database.py).
    import src.db.models  # noqa: F401
    from src.db.database import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def db_session(db_engine) -> Generator[Session, None, None]:
    """A SQLAlchemy session bound to the per-test in-memory database.

    Use this to set up rows directly (e.g. a `CounselorAssignment` — there is
    no API endpoint to grant one) or to assert on rows a request created.
    """
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def app_with_test_db(db_engine):
    """The FastAPI app with `get_db` overridden to use the test database.

    Most tests should use `client` / `make_client` instead of this fixture
    directly; it exists so several independent `TestClient` instances
    (one per authenticated role) can all be wired to the same in-memory DB
    within a single test.
    """
    from src.db.database import get_db
    from src.main import app

    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def _override_get_db() -> Generator[Session, None, None]:
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield app
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def client(app_with_test_db) -> TestClient:
    """Unauthenticated FastAPI test client bound to the test database."""
    return TestClient(app_with_test_db)


# ---------------------------------------------------------------------------
# User / auth fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def auth_header():
    """Factory: `auth_header(user)` -> `{"Authorization": "Bearer <jwt>"}`.

    Useful when a test needs a client WITHOUT a pre-set Authorization header
    (e.g. to test "no token" / "bad token" cases) alongside one that has a
    valid token for comparison.
    """
    from src.core.security import create_access_token

    def _auth_header(user) -> dict[str, str]:
        token = create_access_token(data={"sub": user.id, "role": user.role})
        return {"Authorization": f"Bearer {token}"}

    return _auth_header


@pytest.fixture()
def make_client(app_with_test_db, db_session, auth_header):
    """Factory: `make_client(role="student")` -> authenticated `TestClient`.

    Creates a new `User` row (synthetic email, bcrypt-hashed dummy password)
    directly in the test database and returns a `TestClient` whose default
    headers already carry a valid JWT for that user. The created user is
    reachable via `client.current_user` for tests that need the id/email.

    Call it multiple times in one test to get distinct users (e.g. two
    students, to test cross-user access is forbidden).
    """
    from src.core.security import hash_password
    from src.db.models import User

    def _make_client(role: str = "student", email: str | None = None, full_name: str = "Test User") -> TestClient:
        email = email or f"{role}.{uuid.uuid4().hex[:10]}@example.test"
        user = User(
            email=email,
            hashed_password=hash_password("Sup3r-Secret-Pass!"),
            full_name=full_name,
            role=role,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        test_client = TestClient(app_with_test_db)
        test_client.headers.update(auth_header(user))
        test_client.current_user = user  # type: ignore[attr-defined]
        return test_client

    return _make_client


@pytest.fixture()
def student_client(make_client) -> TestClient:
    return make_client(role="student", full_name="Nguyen Van A")


@pytest.fixture()
def other_student_client(make_client) -> TestClient:
    """A second, distinct student — for cross-user access-denial tests."""
    return make_client(role="student", full_name="Tran Thi B")


@pytest.fixture()
def counselor_client(make_client) -> TestClient:
    return make_client(role="counselor", full_name="Co van C")


@pytest.fixture()
def admin_client(make_client) -> TestClient:
    return make_client(role="admin", full_name="Admin D")


# ---------------------------------------------------------------------------
# DB row helper fixtures (bypass endpoints that are out of scope for a given
# test, e.g. creating a CV without exercising the /cvs/upload parsing path)
# ---------------------------------------------------------------------------


@pytest.fixture()
def make_cv(db_session):
    """Factory: `make_cv(client, **overrides)` -> a `CV` row owned by that client's user."""
    from src.db.models import CV

    def _make_cv(
        owner_client: TestClient, *, title: str = "CV Backend Developer", status: str = "confirmed", **overrides
    ) -> CV:
        cv = CV(
            user_id=owner_client.current_user.id,  # type: ignore[attr-defined]
            title=title,
            raw_text=overrides.pop(
                "raw_text", "Nguyen Van A - Backend Developer. Ky nang: Python, FastAPI, PostgreSQL, Git."
            ),
            parsed_json=overrides.pop(
                "parsed_json",
                {
                    "full_name": "Nguyen Van A",
                    "skills": ["Python", "FastAPI", "PostgreSQL", "Git"],
                    "experience": [{"company": "Cong ty ABC", "description": "Xay dung REST API."}],
                    "education": [{"institution": "Dai hoc Bach Khoa Ha Noi", "degree": "Ky su CNTT"}],
                    "projects": [{"name": "He thong quan ly sinh vien"}],
                },
            ),
            status=status,
            **overrides,
        )
        db_session.add(cv)
        db_session.commit()
        db_session.refresh(cv)
        return cv

    return _make_cv


@pytest.fixture()
def make_jd(db_session):
    """Factory: `make_jd(**overrides)` -> a `JobDescription` row."""
    from src.db.models import JobDescription

    def _make_jd(*, title: str = "Backend Developer (Fresher/Junior)", **overrides) -> JobDescription:
        jd = JobDescription(
            title=title,
            company=overrides.pop("company", "Cong ty XYZ (du lieu gia lap)"),
            location=overrides.pop("location", "Ha Noi"),
            requirements_text=overrides.pop(
                "requirements_text",
                "Yeu cau: Python, FastAPI, PostgreSQL, Git. Uu tien: Docker, Kubernetes.",
            ),
            is_system=overrides.pop("is_system", True),
            **overrides,
        )
        db_session.add(jd)
        db_session.commit()
        db_session.refresh(jd)
        return jd

    return _make_jd


# ---------------------------------------------------------------------------
# Synthetic domain-data fixtures (plain dicts, not DB rows)
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_cv() -> dict[str, Any]:
    """Synthetic parsed CV, shaped like the `cvs.parsed_json` column."""
    return {
        "full_name": "Nguyen Van A",
        "email": "nguyenvana.test@example.com",
        "education": [
            {
                "school": "Dai hoc Bach Khoa Ha Noi",
                "degree": "Ky su Cong nghe thong tin",
                "graduation_year": 2025,
            }
        ],
        "skills": ["Python", "FastAPI", "PostgreSQL", "Git"],
        "experience": [
            {
                "title": "Backend Intern",
                "company": "Cong ty ABC (du lieu gia lap)",
                "duration": "6 thang",
                "description": "Xay dung REST API cho he thong quan ly noi bo.",
            }
        ],
        "projects": [
            {
                "name": "He thong quan ly sinh vien (do an tot nghiep)",
                "description": "Xay dung REST API bang FastAPI va PostgreSQL.",
            }
        ],
    }


@pytest.fixture()
def fake_jd() -> dict[str, Any]:
    """Synthetic job description, shaped like the `job_descriptions.parsed_json` column."""
    return {
        "title": "Backend Developer (Fresher/Junior)",
        "company": "Cong ty XYZ (du lieu gia lap)",
        "location": "Ha Noi",
        "requirements_text": (
            "Yeu cau: Python, FastAPI hoac Django, PostgreSQL, Git. "
            "Uu tien: Docker, Kubernetes, kinh nghiem lam viec voi REST API."
        ),
        "required_skills": ["Python", "FastAPI", "PostgreSQL", "Git"],
        "preferred_skills": ["Docker", "Kubernetes"],
        "required_years_experience": 1,
    }

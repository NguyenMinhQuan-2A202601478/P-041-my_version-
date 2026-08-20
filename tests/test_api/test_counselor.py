"""Tests for /api/v1/counselor/* (F-07: Dashboard Co van huong nghiep, HITL).

There is currently no API endpoint to grant a counselor access to a student
(the PRD/architecture doc describes a future `/students/counselor/grant`
endpoint, but `src/api/routes.py` does not wire up any such router yet).
These tests create the `CounselorAssignment` row directly via `db_session` —
this is exactly the access-control gate `_assert_assigned()` in
`src/api/v1/counselor.py` checks, so it is the right thing to set up
directly regardless of which endpoint eventually creates it.
"""

from __future__ import annotations


def _grant_access(db_session, counselor_client, student_client, status: str = "active"):
    from src.db.models import CounselorAssignment

    assignment = CounselorAssignment(
        counselor_id=counselor_client.current_user.id,
        student_id=student_client.current_user.id,
        status=status,
    )
    db_session.add(assignment)
    db_session.commit()
    db_session.refresh(assignment)
    return assignment


def test_counselor_can_list_assigned_students(db_session, counselor_client, student_client):
    _grant_access(db_session, counselor_client, student_client)

    response = counselor_client.get("/api/v1/counselor/students")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["student_id"] == student_client.current_user.id


def test_counselor_list_students_excludes_unassigned(counselor_client, student_client):
    """No assignment was created, so the counselor's roster is empty —
    never leaking every student in the system."""
    response = counselor_client.get("/api/v1/counselor/students")

    assert response.status_code == 200
    assert response.json() == []


def test_counselor_can_view_assigned_students_progress(db_session, counselor_client, student_client, make_cv):
    _grant_access(db_session, counselor_client, student_client)
    make_cv(student_client)

    response = counselor_client.get(f"/api/v1/counselor/students/{student_client.current_user.id}/progress")

    assert response.status_code == 200
    body = response.json()
    assert body["total_cvs"] == 1


def test_counselor_cannot_view_unassigned_students_progress(counselor_client, student_client):
    response = counselor_client.get(f"/api/v1/counselor/students/{student_client.current_user.id}/progress")
    assert response.status_code == 403


def test_counselor_cannot_view_progress_after_revoked_access(db_session, counselor_client, student_client):
    _grant_access(db_session, counselor_client, student_client, status="revoked")

    response = counselor_client.get(f"/api/v1/counselor/students/{student_client.current_user.id}/progress")

    assert response.status_code == 403


def test_student_cannot_access_counselor_endpoints(student_client):
    response = student_client.get("/api/v1/counselor/students")
    assert response.status_code == 403


def test_student_cannot_access_counselor_dashboard(student_client):
    response = student_client.get("/api/v1/counselor/dashboard")
    assert response.status_code == 403


def test_counselor_can_send_feedback_to_assigned_student(db_session, counselor_client, student_client):
    _grant_access(db_session, counselor_client, student_client)

    response = counselor_client.post(
        f"/api/v1/counselor/students/{student_client.current_user.id}/feedback",
        json={"kind": "comment", "content": "Ban nen bo sung them so lieu cu the trong phan kinh nghiem."},
    )

    assert response.status_code == 201
    assert "id" in response.json()


def test_counselor_cannot_send_feedback_to_unassigned_student(counselor_client, student_client):
    response = counselor_client.post(
        f"/api/v1/counselor/students/{student_client.current_user.id}/feedback",
        json={"kind": "comment", "content": "Nhan xet"},
    )
    assert response.status_code == 403


def test_counselor_dashboard_aggregates_assigned_students(db_session, counselor_client, student_client):
    _grant_access(db_session, counselor_client, student_client)

    response = counselor_client.get("/api/v1/counselor/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["total_students"] == 1
    assert body["total_cvs_optimized"] == 0
    assert body["total_interviews"] == 0


def test_admin_can_access_counselor_endpoints(admin_client):
    """role_required("counselor", "admin") allows admin through even with
    zero assignments — dashboard should just report empty stats, not 403."""
    response = admin_client.get("/api/v1/counselor/students")
    assert response.status_code == 200

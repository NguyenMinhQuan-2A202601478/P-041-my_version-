"""Student-side counselor access management (F-07 prerequisite).

Students grant/revoke counselor access to their data here. Without an
active CounselorAssignment row, no counselor endpoint in counselor.py
can access a student's CV/analysis/interview data.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.core.security import get_current_user, role_required
from src.db.database import get_db
from src.db.models import CounselorAssignment, CounselorFeedback, User

router = APIRouter(prefix="/students", tags=["students"])


@router.post("/counselor/grant", status_code=status.HTTP_201_CREATED)
def grant_counselor_access(
    counselor_id: str,
    current_user: User = Depends(role_required("student")),
    db: Session = Depends(get_db),
) -> dict:
    """Student grants a counselor access to their data."""
    counselor = db.get(User, counselor_id)
    if counselor is None or counselor.role != "counselor":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay co van"
        )

    existing = (
        db.query(CounselorAssignment)
        .filter(
            CounselorAssignment.counselor_id == counselor_id,
            CounselorAssignment.student_id == current_user.id,
            CounselorAssignment.status == "active",
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Co van nay da duoc cap quyen truy cap",
        )

    revoked = (
        db.query(CounselorAssignment)
        .filter(
            CounselorAssignment.counselor_id == counselor_id,
            CounselorAssignment.student_id == current_user.id,
            CounselorAssignment.status == "revoked",
        )
        .first()
    )
    if revoked is not None:
        revoked.status = "active"
        revoked.revoked_at = None
        db.commit()
        return {"id": revoked.id, "status": "active", "message": "Da cap lai quyen truy cap"}

    assignment = CounselorAssignment(
        counselor_id=counselor_id,
        student_id=current_user.id,
        status="active",
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return {"id": assignment.id, "status": "active", "message": "Da cap quyen truy cap cho co van"}


@router.delete("/counselor/{assignment_id}")
def revoke_counselor_access(
    assignment_id: str,
    current_user: User = Depends(role_required("student")),
    db: Session = Depends(get_db),
) -> dict:
    """Student revokes a counselor's access to their data."""
    assignment = db.get(CounselorAssignment, assignment_id)
    if assignment is None or assignment.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay quyen truy cap"
        )
    if assignment.status == "revoked":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Quyen truy cap da bi thu hoi truoc do"
        )

    assignment.status = "revoked"
    assignment.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "Da thu hoi quyen truy cap cua co van"}


@router.get("/counselor/feedback")
def get_my_feedback(
    current_user: User = Depends(role_required("student")),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Student views all feedback from their counselors."""
    feedbacks = (
        db.query(CounselorFeedback)
        .filter(CounselorFeedback.student_id == current_user.id)
        .order_by(CounselorFeedback.created_at.desc())
        .all()
    )
    return [
        {
            "id": fb.id,
            "counselor_id": fb.counselor_id,
            "kind": fb.kind,
            "content": fb.content,
            "created_at": fb.created_at.isoformat(),
        }
        for fb in feedbacks
    ]

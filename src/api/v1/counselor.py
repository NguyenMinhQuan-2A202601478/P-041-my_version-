"""Counselor Dashboard (F-07): danh sach SV duoc cap quyen, tien do, bao cao, phan hoi.

Phan quyen: MOI route trong file nay yeu cau role "counselor" hoac "admin"
(xem `dependencies=[Depends(role_required(...))]` tren APIRouter ben duoi).
Ngoai ra, moi truy cap toi du lieu 1 sinh vien cu the con phai qua
`_assert_assigned()` — co van CHI duoc xem SV da CHU DONG cap quyen (bang
`counselor_assignments`, status="active"). Day la yeu cau bat buoc theo
CLAUDE.md cua du an: "Du lieu CV ca nhan phai phan quyen theo role. Khong lo
cheo du lieu."
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.core.security import get_current_user, role_required
from src.db.database import get_db
from src.db.models import (
    CV,
    CounselorAssignment,
    CounselorFeedback,
    CVAnalysis,
    InterviewReport,
    InterviewSession,
    User,
)
from src.models.schemas import (
    CounselorDashboardResponse,
    CounselorFeedbackRequest,
    CounselorFeedbackResponse,
    StudentProgressResponse,
    StudentSummary,
)

router = APIRouter(
    prefix="/counselor",
    tags=["counselor"],
    dependencies=[Depends(role_required("counselor", "admin"))],
)


def _assert_assigned(counselor_id: str, student_id: str, db: Session) -> CounselorAssignment:
    """Chan truy cap (403) neu co van chua duoc SV nay cap quyen (hoac quyen da bi thu hoi)."""
    assignment = (
        db.query(CounselorAssignment)
        .filter(
            CounselorAssignment.counselor_id == counselor_id,
            CounselorAssignment.student_id == student_id,
            CounselorAssignment.status == "active",
        )
        .first()
    )
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ban chua duoc sinh vien nay cap quyen xem du lieu",
        )
    return assignment


@router.get("/students", response_model=list[StudentSummary])
def list_students(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[StudentSummary]:
    assignments = (
        db.query(CounselorAssignment)
        .filter(CounselorAssignment.counselor_id == current_user.id, CounselorAssignment.status == "active")
        .all()
    )
    student_ids = [a.student_id for a in assignments]
    if not student_ids:
        return []

    students = db.query(User).filter(User.id.in_(student_ids)).all()
    return [StudentSummary(student_id=s.id, full_name=s.full_name, email=s.email, status="active") for s in students]


@router.get("/dashboard", response_model=CounselorDashboardResponse)
def get_dashboard(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> CounselorDashboardResponse:
    """Thong ke tong hop tren toan bo SV duoc phan cong cho co van dang nhap."""
    student_ids = [
        a.student_id
        for a in db.query(CounselorAssignment)
        .filter(CounselorAssignment.counselor_id == current_user.id, CounselorAssignment.status == "active")
        .all()
    ]

    total_cvs_optimized = 0
    total_interviews = 0
    scores: list[float] = []
    if student_ids:
        total_cvs_optimized = db.query(CVAnalysis).filter(CVAnalysis.user_id.in_(student_ids)).count()
        sessions = db.query(InterviewSession).filter(InterviewSession.user_id.in_(student_ids)).all()
        total_interviews = len(sessions)
        for session in sessions:
            report = db.query(InterviewReport).filter(InterviewReport.session_id == session.id).first()
            if report:
                scores.append(report.total_score)

    return CounselorDashboardResponse(
        total_students=len(student_ids),
        total_cvs_optimized=total_cvs_optimized,
        total_interviews=total_interviews,
        avg_score=(sum(scores) / len(scores)) if scores else None,
    )


@router.get("/students/{student_id}/progress", response_model=StudentProgressResponse)
def get_student_progress(
    student_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> StudentProgressResponse:
    _assert_assigned(current_user.id, student_id, db)

    total_cvs = db.query(CV).filter(CV.user_id == student_id).count()
    total_analyses = db.query(CVAnalysis).filter(CVAnalysis.user_id == student_id).count()
    sessions = db.query(InterviewSession).filter(InterviewSession.user_id == student_id).all()

    scores = []
    for session in sessions:
        report = db.query(InterviewReport).filter(InterviewReport.session_id == session.id).first()
        if report:
            scores.append(report.total_score)

    return StudentProgressResponse(
        student_id=student_id,
        total_cvs=total_cvs,
        total_analyses=total_analyses,
        total_interviews=len(sessions),
        avg_interview_score=(sum(scores) / len(scores)) if scores else None,
    )


@router.get("/students/{student_id}/reports")
def get_student_reports(
    student_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[dict]:
    """Lich su bao cao phong van STAR cua 1 SV — dung dict thay vi schema rieng
    vi day la view tong hop don gian cho co van, khong phai contract public API chinh.
    """
    _assert_assigned(current_user.id, student_id, db)

    sessions = db.query(InterviewSession).filter(InterviewSession.user_id == student_id).all()
    results = []
    for session in sessions:
        report = db.query(InterviewReport).filter(InterviewReport.session_id == session.id).first()
        if report is not None:
            results.append(
                {
                    "session_id": session.id,
                    "jd_title": session.jd.title if session.jd else "",
                    "total_score": report.total_score,
                    "star_scores": report.star_scores_json,
                    "strengths": report.strengths_json,
                    "improvements": report.improvements_json,
                    "created_at": report.created_at,
                }
            )
    return results


@router.post(
    "/students/{student_id}/feedback",
    response_model=CounselorFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
def send_feedback(
    student_id: str,
    payload: CounselorFeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CounselorFeedbackResponse:
    assignment = _assert_assigned(current_user.id, student_id, db)

    feedback = CounselorFeedback(
        assignment_id=assignment.id,
        counselor_id=current_user.id,
        student_id=student_id,
        interview_report_id=payload.interview_report_id,
        kind=payload.kind,
        content=payload.content,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return CounselorFeedbackResponse(id=feedback.id, created_at=feedback.created_at)

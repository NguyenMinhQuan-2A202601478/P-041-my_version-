"""Job Description management (F-03): thu vien JD he thong + SV dan JD ngoai."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.core.security import get_current_user
from src.db.database import get_db
from src.db.models import JobDescription, User
from src.models.schemas import JDCreateRequest, JDResponse, JDSummary

router = APIRouter(prefix="/jds", tags=["jds"])


@router.get("/", response_model=list[JDSummary])
def list_jds(
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[JobDescription]:
    """Danh sach JD — moi user da dang nhap deu xem duoc (JD khong phai du lieu ca nhan)."""
    query = db.query(JobDescription)
    if search:
        query = query.filter(JobDescription.title.ilike(f"%{search}%"))
    return query.order_by(JobDescription.created_at.desc()).all()


@router.post("/paste", response_model=JDResponse, status_code=status.HTTP_201_CREATED)
def paste_jd(
    payload: JDCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobDescription:
    jd = JobDescription(
        title=payload.title,
        company=payload.company,
        location=payload.location,
        requirements_text=payload.requirements_text,
        is_system=False,
        created_by_user_id=current_user.id,
    )
    db.add(jd)
    db.commit()
    db.refresh(jd)
    return jd


@router.get("/{jd_id}", response_model=JDResponse)
def get_jd(jd_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> JobDescription:
    jd = db.get(JobDescription, jd_id)
    if jd is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay JD")
    return jd

"""CV management (F-02): upload PDF/DOCX (<=10MB), xem, liet ke, xoa CV."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from src.config import settings
from src.core.security import get_current_user
from src.db.database import get_db
from src.db.models import CV, User
from src.models.schemas import CVDetailResponse, CVSummary, CVUploadResponse
from src.services.cv_parser import parse_cv

router = APIRouter(prefix="/cvs", tags=["cvs"])


def _validate_upload(file: UploadFile, content: bytes) -> None:
    """Kiem tra dinh dang file (chi PDF/DOCX) va dung luong (<= MAX_UPLOAD_SIZE_MB)."""
    filename = (file.filename or "").lower()
    if not filename.endswith(settings.ALLOWED_CV_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chi chap nhan file dinh dang {', '.join(settings.ALLOWED_CV_EXTENSIONS)}",
        )
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File vuot qua gioi han {settings.MAX_UPLOAD_SIZE_MB}MB",
        )
    if len(content) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File rong")


def _get_owned_cv(cv_id: str, current_user: User, db: Session) -> CV:
    """Lay CV theo id, dam bao chi chinh chu (hoac admin) moi truy cap duoc.

    Day la phan quyen theo du lieu (data-level authorization) — bat buoc
    theo CLAUDE.md cua du an ("Du lieu CV ca nhan phai phan quyen theo role,
    khong lo cheo du lieu").
    """
    cv = db.get(CV, cv_id)
    if cv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay CV")
    if cv.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Khong co quyen truy cap CV nay")
    return cv


@router.post("/upload", response_model=CVUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_cv(
    file: UploadFile = File(...),
    title: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CV:
    content = await file.read()
    _validate_upload(file, content)

    parsed = await parse_cv(content, file.filename)
    raw_text = parsed["raw_text"]
    parsed_json = parsed["parsed_json"]

    cv = CV(
        user_id=current_user.id,
        title=title,
        raw_text=raw_text,
        parsed_json=parsed_json,
        status="draft",
    )
    db.add(cv)
    db.commit()
    db.refresh(cv)
    return cv


@router.get("/", response_model=list[CVSummary])
def list_cvs(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[CV]:
    """Chi tra ve CV cua chinh user dang goi API (khong bao gio tra ve CV cua user khac)."""
    return db.query(CV).filter(CV.user_id == current_user.id).order_by(CV.created_at.desc()).all()


@router.get("/{cv_id}", response_model=CVDetailResponse)
def get_cv(cv_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> CV:
    return _get_owned_cv(cv_id, current_user, db)


@router.put("/{cv_id}/confirm", response_model=CVDetailResponse)
def confirm_cv(cv_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> CV:
    """SV xac nhan noi dung da trich xuat (parsed_json) la dung truoc khi dung de phan tich/phong van."""
    cv = _get_owned_cv(cv_id, current_user, db)
    cv.status = "confirmed"
    db.commit()
    db.refresh(cv)
    return cv


@router.delete("/{cv_id}")
def delete_cv(cv_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    cv = _get_owned_cv(cv_id, current_user, db)
    db.delete(cv)
    db.commit()
    return {"message": "Deleted"}

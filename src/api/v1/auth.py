"""Auth endpoints (F-01): dang ky, dang nhap, Google OAuth, thong tin user hien tai."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.config import settings
from src.core.security import create_access_token, get_current_user, hash_password, verify_password
from src.db.database import get_db
from src.db.models import User
from src.models.schemas import (
    GoogleAuthRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> User:
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email da duoc su dung")

    # Self-registration chi cho phep role "student". Counselor/admin phai
    # duoc tao boi admin qua endpoint rieng (hoac seed script).
    role = "student"

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        # Co y KHONG noi ro "sai email" hay "sai mat khau" de tranh lo thong
        # tin cho ke tan cong biet email nao da ton tai trong he thong.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoac mat khau khong dung",
        )

    access_token = create_access_token(
        data={"sub": user.id, "role": user.role},
        expires_delta=timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    )
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.post("/google", response_model=TokenResponse)
def google_login(payload: GoogleAuthRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Dang nhap bang Google OAuth.

    LUU Y TRIEN KHAI: route nay dinh nghia dung request/response schema
    theo API Contract, nhung phan xac minh `google_token` voi Google (goi
    Google tokeninfo API, kiem tra `aud` khop GOOGLE_CLIENT_ID) se duoc wire
    khi co GOOGLE_CLIENT_ID/SECRET that. KHONG duoc tin token ma khong xac
    minh — tam thoi tra ve 501 de khong ai vo tinh dung 1 luong xac thuc
    chua an toan trong production.
    """
    _ = (payload, db)  # tham so se duoc dung khi wire xac minh Google that
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Google OAuth chua duoc trien khai day du",
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user

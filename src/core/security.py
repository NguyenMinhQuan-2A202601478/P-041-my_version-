"""JWT authentication va password hashing.

Vi sao can JWT (JSON Web Token)? JWT la 1 "ve thong hanh" server cap cho
user ngay sau khi dang nhap thanh cong. User gui kem token nay trong header
`Authorization: Bearer <token>` o moi request tiep theo de chung minh "toi
da dang nhap roi". Server KHONG can luu session trong database — chi can
giai ma (decode) token la biet ngay user_id va role, giup he thong de mo
rong (khong can dong bo session giua nhieu server).

Vi sao khong luu mat khau goc? Neu database bi lo (hack), ke xau se co toan
bo mat khau nguoi dung neu ta luu plaintext. bcrypt la 1 ham "bam mot
chieu" (hash) — khong the giai nguoc tu hash ra mat khau goc, nen du DB bi
lo, mat khau that van an toan (kho brute-force nho bcrypt co "cost factor"
lam cham qua trinh do).
"""

from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from src.config import settings
from src.db.database import get_db
from src.db.models import User

# OAuth2PasswordBearer bao FastAPI: (1) lay token tu header
# "Authorization: Bearer <token>", (2) o Swagger UI (/docs), hien nut
# "Authorize" tro toi endpoint login duoi day de lay token thu.
# auto_error=False de ta tu kiem soat thong bao loi trong get_current_user().
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login", auto_error=False)

_BCRYPT_MAX_BYTES = 72  # bcrypt chi xu ly toi da 72 byte dau cua mat khau


def hash_password(password: str) -> str:
    """Bam (hash) mat khau bang bcrypt truoc khi luu vao DB.

    KHONG BAO GIO luu mat khau goc (plaintext) vao database.
    """
    pwd_bytes = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """So sanh mat khau nguoi dung nhap luc dang nhap voi hash da luu trong DB."""
    try:
        pwd_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except (ValueError, TypeError):
        # Hash bi hong/khong dung dinh dang bcrypt -> coi nhu xac thuc that bai,
        # khong de loi nay lam sap request dang nhap.
        return False


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Tao JWT access token chua thong tin user (vd: sub=user_id, role) va han su dung."""
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """Giai ma va xac thuc chu ky cua JWT token.

    Nem HTTPException(401) neu token khong hop le, bi sua doi, hoac da het han.
    """
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token khong hop le hoac da het han",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency: lay user hien tai tu JWT token trong header Authorization.

    Cach dung trong 1 route: `current_user: User = Depends(get_current_user)`.
    FastAPI se tu dong: doc header Authorization -> goi ham nay -> neu hop
    le, dua User vao tham so `current_user`; neu khong, tra ve 401 truoc
    khi code trong route duoc chay.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Chua dang nhap hoac token khong hop le",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    payload = verify_token(token)
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    user = db.get(User, user_id)
    if user is None:
        raise credentials_exception
    return user


def role_required(*allowed_roles: str):
    """Dependency factory: gioi han 1 route chi cho phep 1 so role nhat dinh goi.

    Vi du: `Depends(role_required("counselor", "admin"))` tren 1 router se
    khien MOI route trong router do tra ve 403 Forbidden neu user dang nhap
    khong phai counselor hoac admin (vd: student bi chan khoi Dashboard co van).
    """

    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Yeu cau quyen: {', '.join(allowed_roles)}",
            )
        return current_user

    return checker

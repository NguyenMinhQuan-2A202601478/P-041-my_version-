"""Database connection setup (SQLAlchemy).

Giai thich cho nguoi moi hoc CSDL:
- "Engine" la doi tuong dai dien cho 1 ket noi toi database (biet database o
  dau, dung driver nao de noi chuyen voi no).
- "Session" la 1 "phien lam viec" voi database — ban mo session, doc/ghi du
  lieu, roi dong session lai. Moi request API nen dung 1 session rieng de
  tranh xung dot du lieu giua cac request chay dong thoi.
- "ORM" (Object-Relational Mapping) cho phep ta thao tac database bang code
  Python (vi du `User(email="a@b.com")`) thay vi tu viet cau lenh SQL.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config import settings

# --- Engine ---
# SQLite mac dinh chi cho phep connection duoc tao ra va dung tren CUNG 1
# thread. FastAPI (khi chay route dong bo/sync) co the xu ly request tren
# nhieu thread khac nhau trong threadpool, nen can tat kiem tra nay
# (check_same_thread=False) rieng cho SQLite. PostgreSQL khong co gioi han
# nay nen khong can flag.
connect_args: dict = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=settings.DATABASE_ECHO,
    # pool_pre_ping: truoc khi dung 1 connection tu pool, SQLAlchemy se "ping"
    # thu de chac chan connection con song. Giup tranh loi "connection da bi
    # dong" khi database (dac biet PostgreSQL tren cloud) ngu lau roi ngat
    # ket noi nhan roi.
    pool_pre_ping=True,
    future=True,
)

# Session factory: moi lan goi SessionLocal() se tao ra 1 Session moi (1
# "phien lam viec" doc lap voi database).
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


class Base(DeclarativeBase):
    """Lop co so (base class) cho tat ca ORM models dinh nghia trong db/models.py.

    Moi bang trong database se duoc khai bao nhu 1 class ke thua tu Base nay.
    """


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: cung cap 1 Session cho moi request.

    Cach dung trong 1 route: `db: Session = Depends(get_db)`.
    FastAPI se tu dong goi ham nay truoc khi chay route, dua Session vao, va
    dam bao Session duoc dong lai (kem don dep tai nguyen) sau khi request
    ket thuc — ke ca khi route bi loi (nho khoi `finally`).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """Tao tat ca cac bang trong database neu chung chua ton tai.

    Duoc goi 1 lan khi ung dung khoi dong (xem `lifespan` trong src/main.py).

    Luu y cho du an that: voi 1 team lon hoac production co nhieu ban phat
    hanh, nen dung cong cu migration (vi du Alembic) de thay doi cau truc
    database theo tung buoc co kiem soat, thay vi create_all(). Nhung voi
    MVP nay, create_all() (tao bang neu chua co, khong dong gi neu da co) la
    du dung va don gian hon nhieu.
    """
    # Import models NGAY TAI DAY (khong phai o dau file) de tranh vong lap
    # import (circular import): models.py can import `Base` tu file nay, neu
    # ta import models.py o dau database.py thi 2 file se import lan nhau
    # truoc khi ca 2 duoc dinh nghia xong.
    from src.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

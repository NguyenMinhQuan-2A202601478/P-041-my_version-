"""SQLAlchemy ORM models — moi class ben duoi tuong ung 1 bang trong database.

Bang du lieu la gi? Hay tuong tuong 1 bang tinh Excel: moi class o day la 1
"sheet" (bang), moi thuoc tinh (attribute) la 1 "cot", va moi ban ghi (row)
la 1 dong du lieu cu the. SQLAlchemy (ORM — Object-Relational Mapping) cho
phep ta doc/ghi du lieu bang code Python (vi du `User(email="a@b.com")`)
thay vi phai tu tay viet cau lenh SQL nhu `INSERT INTO users (...) VALUES (...)`.

Cac bang o day duoc thiet ke theo `docs/architecture/system_architecture.md`
(Section 3 — Database Schema), la tai lieu kien truc da duoc duyet.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.database import Base


def _uuid() -> str:
    """Sinh UUID (Universally Unique Identifier) de lam khoa chinh (primary key).

    Vi sao dung UUID (chuoi ngau nhien nhu "3f2a9c...") thay vi so tu tang
    dan (1, 2, 3...)? (1) Khong doan duoc — nguoi ngoai khong the doan
    "id=5 la ban ghi tiep theo sau id=4". (2) An toan hon khi id duoc expose
    qua API. (3) Khong bi trung id neu sau nay he thong chay tren nhieu
    server/database cung luc.
    """
    return uuid.uuid4().hex


class User(Base):
    """Bang `users` — tai khoan cua sinh vien, co van, doanh nghiep, admin.

    Moi hanh dong tren he thong deu can biet "ai dang lam" de: (1) luu du
    lieu dung chu so huu, (2) phan quyen (student chi xem duoc du lieu cua
    chinh minh, counselor chi xem SV da cap quyen...).
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # Nullable vi user dang nhap bang Google OAuth co the khong co mat khau.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # student | counselor | enterprise | admin — xem role_required() trong core/security.py
    role: Mapped[str] = mapped_column(String(50), default="student", nullable=False)
    oauth_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)  # vd: "google"
    oauth_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # relationship(): khong tao them cot nao trong DB, chi giup code Python
    # de doc hon — vd `user.cvs` tra ve danh sach CV cua user do, SQLAlchemy
    # tu dong sinh cau JOIN can thiet phia sau.
    cvs: Mapped[list["CV"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    analyses: Mapped[list["CVAnalysis"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    interview_sessions: Mapped[list["InterviewSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class CV(Base):
    """Bang `cvs` — moi ban CV (van ban tho + du lieu da parse) SV upload."""

    __tablename__ = "cvs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Cot kieu JSON: luu du lieu ban cau truc (vd {"skills": [...], "experience": [...]})
    # ma khong can tao them bang rieng cho tung truong con — phu hop vi cau
    # truc CV co the thay doi theo tung phien ban parser.
    parsed_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)  # draft | confirmed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="cvs")
    analyses: Mapped[list["CVAnalysis"]] = relationship(back_populates="cv", cascade="all, delete-orphan")
    interview_sessions: Mapped[list["InterviewSession"]] = relationship(
        back_populates="cv", cascade="all, delete-orphan"
    )


class JobDescription(Base):
    """Bang `job_descriptions` — JD tu thu vien he thong hoac SV dan tu ben ngoai."""

    __tablename__ = "job_descriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requirements_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    analyses: Mapped[list["CVAnalysis"]] = relationship(back_populates="jd", cascade="all, delete-orphan")
    interview_sessions: Mapped[list["InterviewSession"]] = relationship(
        back_populates="jd", cascade="all, delete-orphan"
    )


class CVAnalysis(Base):
    """Bang `cv_analyses` — ket qua Gap Analysis (so khop CV voi JD) cua 1 lan chay.

    Duoc luu lai de SV xem lich su, co van theo doi tien do, va so sanh
    truoc/sau khi toi uu CV.
    """

    __tablename__ = "cv_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cv_id: Mapped[str] = mapped_column(String(36), ForeignKey("cvs.id", ondelete="CASCADE"), nullable=False, index=True)
    jd_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("job_descriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    match_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # 0-100
    gap_analysis_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    suggestions_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="analyses")
    cv: Mapped["CV"] = relationship(back_populates="analyses")
    jd: Mapped["JobDescription"] = relationship(back_populates="analyses")
    decisions: Mapped[list["OptimizationDecision"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )


class OptimizationDecision(Base):
    """Bang `optimization_decisions` — quyet dinh Accept/Reject cua SV cho tung goi y.

    Day chinh la co che HITL (Human-in-the-Loop) bat buoc theo CLAUDE.md cua
    du an: AI CHI de xuat, KHONG bao gio tu dong sua noi dung CV. Sinh vien
    la nguoi bam Accept/Reject va chiu trach nhiem cuoi cung ve noi dung CV.
    """

    __tablename__ = "optimization_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    cv_id: Mapped[str] = mapped_column(String(36), ForeignKey("cvs.id", ondelete="CASCADE"), nullable=False)
    analysis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cv_analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    suggestion_index: Mapped[int] = mapped_column(Integer, nullable=False)  # vi tri goi y trong suggestions_json
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    final_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # SV co the sua truoc khi Accept
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    analysis: Mapped["CVAnalysis"] = relationship(back_populates="decisions")


class InterviewSession(Base):
    """Bang `interview_sessions` — 1 phien phong van thu (gom 5-7 cau hoi)."""

    __tablename__ = "interview_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cv_id: Mapped[str] = mapped_column(String(36), ForeignKey("cvs.id", ondelete="CASCADE"), nullable=False)
    jd_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("job_descriptions.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), default="ongoing", nullable=False)  # ongoing|completed|cancelled
    total_questions: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    current_question_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="interview_sessions")
    cv: Mapped["CV"] = relationship(back_populates="interview_sessions")
    jd: Mapped["JobDescription"] = relationship(back_populates="interview_sessions")
    questions: Mapped[list["InterviewQuestion"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="InterviewQuestion.question_index",
    )
    report: Mapped["InterviewReport | None"] = relationship(
        back_populates="session", uselist=False, cascade="all, delete-orphan"
    )


class InterviewQuestion(Base):
    """Bang `interview_questions` — tung cau hoi/cau tra loi/diem STAR trong 1 phien."""

    __tablename__ = "interview_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    user_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Diem STAR (Situation/Task/Action/Result) cho rieng cau hoi nay, vd:
    # {"situation": 20, "task": 25, "action": 30, "result": 15}
    star_score_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["InterviewSession"] = relationship(back_populates="questions")


class InterviewReport(Base):
    """Bang `interview_reports` — bao cao tong hop sau khi phien phong van hoan thanh.

    Moi phien phong van chi co DUY NHAT 1 bao cao (unique=True tren session_id).
    """

    __tablename__ = "interview_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("interview_sessions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    total_score: Mapped[float] = mapped_column(Float, nullable=False)  # thang 100
    # Diem trung binh tung tieu chi STAR toan phien, vd:
    # {"situation": {"avg_score": 18.5, "max": 25, "feedback": "..."}, ...}
    star_scores_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    strengths_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    improvements_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    recommendations_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)  # goi y cau tra loi mau
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["InterviewSession"] = relationship(back_populates="report")


class CounselorAssignment(Base):
    """Bang `counselor_assignments` — quyen 1 co van duoc xem du lieu cua 1 sinh vien.

    Day la co che bao ve quyen rieng tu bat buoc theo CLAUDE.md ("Khong lo
    cheo du lieu"): co van CHI duoc xem SV da CHU DONG cap quyen (status =
    "active"). Khi SV thu hoi quyen, status chuyen thanh "revoked" va co
    van khong con truy cap duoc nua (xem _assert_assigned trong
    api/v1/counselor.py).
    """

    __tablename__ = "counselor_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    counselor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # active | revoked
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CounselorFeedback(Base):
    """Bang `counselor_feedback` — nhan xet/bai tap co van gui cho sinh vien."""

    __tablename__ = "counselor_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    assignment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("counselor_assignments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    counselor_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    interview_report_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("interview_reports.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(20), default="comment", nullable=False)  # comment | task
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

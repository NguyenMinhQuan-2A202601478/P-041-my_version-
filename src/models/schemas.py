"""Pydantic request/response schemas cho REST API.

Pydantic tu dong: (1) validate du lieu dau vao — vd tu choi neu password qua
ngan hoac thieu truong bat buoc; (2) chuyen doi giua du lieu Python va JSON
khi tra ve cho frontend. Day la lop "hop dong" (contract) giua Backend va
Frontend: ca 2 phia deu biet chinh xac 1 request/response se co hinh dang gi.

Thiet ke theo `docs/architecture/system_architecture.md` Section 4 (API
Contract).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Regex don gian de kiem tra dinh dang email co ban (vd "a@b.com"), khong
# dung `pydantic.EmailStr` vi thu vien `email-validator` ma no can chua
# duoc cai trong du an nay (goi y: agent_qa co the them sau vao pyproject.toml
# neu can validate email chat che hon).
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


# --------------------------------------------------------------------------
# Auth (F-01)
# --------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: str = Field(pattern=_EMAIL_PATTERN)
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)
    role: str = "student"  # student | counselor | enterprise | admin


class LoginRequest(BaseModel):
    email: str = Field(pattern=_EMAIL_PATTERN)
    password: str


class GoogleAuthRequest(BaseModel):
    google_token: str


class UserResponse(BaseModel):
    # from_attributes=True cho phep Pydantic doc truc tiep tu 1 doi tuong
    # ORM (vd `User` trong db/models.py) thay vi chi tu dict, mien la ten
    # thuoc tinh khop nhau.
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    role: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# --------------------------------------------------------------------------
# CV (F-02)
# --------------------------------------------------------------------------


class CVUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    raw_text: str | None = None
    parsed_json: dict[str, Any] | None = None
    status: str
    created_at: datetime


class CVDetailResponse(CVUploadResponse):
    updated_at: datetime


class CVSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    status: str
    created_at: datetime


CVListResponse = list[CVSummary]


# --------------------------------------------------------------------------
# Job Description / JD (F-03)
# --------------------------------------------------------------------------


class JDCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    company: str | None = None
    location: str | None = None
    requirements_text: str = Field(min_length=1)


class JDResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    company: str | None = None
    location: str | None = None
    requirements_text: str
    parsed_json: dict[str, Any] | None = None
    is_system: bool
    created_at: datetime


class JDSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    company: str | None = None
    location: str | None = None
    created_at: datetime


JDListResponse = list[JDSummary]


# --------------------------------------------------------------------------
# Gap Analysis (F-03, F-04)
# --------------------------------------------------------------------------


class GapAnalysisRequest(BaseModel):
    cv_id: str
    jd_id: str


class GapAnalysisResponse(BaseModel):
    id: str
    cv_id: str
    jd_id: str
    match_score: float
    gap_analysis: dict[str, Any] | None = None
    suggestions: list[dict[str, Any]] | None = None
    created_at: datetime


class SuggestionDecisionRequest(BaseModel):
    """Body cho POST /analysis/{id}/decide — Accept/Reject 1 goi y toi uu CV (HITL)."""

    suggestion_index: int = Field(ge=0)
    accepted: bool
    final_text: str | None = None  # SV co the tu chinh sua truoc khi Accept


class SuggestionDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    suggestion_index: int
    accepted: bool
    final_text: str | None = None


class AnalysisHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    cv_id: str
    jd_id: str
    match_score: float
    created_at: datetime


AnalysisHistoryResponse = list[AnalysisHistoryItem]


# --------------------------------------------------------------------------
# Mock Interview (F-05, F-06)
# --------------------------------------------------------------------------


class InterviewStartRequest(BaseModel):
    cv_id: str
    jd_id: str
    total_questions: int = Field(default=5, ge=5, le=7)


class QuestionOut(BaseModel):
    index: int
    text: str


class InterviewStartResponse(BaseModel):
    session_id: str
    status: str
    total_questions: int
    current_index: int
    first_question: QuestionOut


class InterviewRespondRequest(BaseModel):
    answer: str = Field(min_length=1)


class InterviewRespondResponse(BaseModel):
    current_index: int
    is_follow_up: bool
    status: str
    next_question: QuestionOut | None = None


class InterviewStatusResponse(BaseModel):
    session_id: str
    status: str
    current_index: int
    total_questions: int


class STARCriterionScore(BaseModel):
    """1 tieu chi trong rubric STAR (Situation/Task/Action/Result).

    Luu y cho agent_ai: `star_scores_json` trong bang `interview_reports`
    nen luu 1 dict voi 4 khoa "situation"|"task"|"action"|"result", moi gia
    tri co dang {"score": float, "max": float, "feedback": str} de khop voi
    schema nay khi API doc lai va tra ve cho frontend.
    """

    score: float
    max: float = 25.0
    feedback: str | None = None


class InterviewReportResponse(BaseModel):
    session_id: str
    total_score: float
    star_scores: dict[str, STARCriterionScore] | None = None
    strengths: list[str] | None = None
    improvements: list[str] | None = None
    recommendations: list[dict[str, Any]] | None = None


class InterviewHistoryItem(BaseModel):
    session_id: str
    jd_title: str
    total_score: float | None = None
    status: str
    created_at: datetime


InterviewHistoryResponse = list[InterviewHistoryItem]


# --------------------------------------------------------------------------
# Counselor Dashboard (F-07)
# --------------------------------------------------------------------------


class StudentSummary(BaseModel):
    student_id: str
    full_name: str
    email: str
    status: str


StudentListResponse = list[StudentSummary]


class StudentProgressResponse(BaseModel):
    student_id: str
    total_cvs: int
    total_analyses: int
    total_interviews: int
    avg_interview_score: float | None = None


class CounselorFeedbackRequest(BaseModel):
    """Body cho POST /counselor/students/{student_id}/feedback.

    `student_id` khong can lap lai o day vi da co trong URL path.
    """

    kind: str = "comment"  # comment | task
    content: str = Field(min_length=1)
    interview_report_id: str | None = None


class CounselorFeedbackResponse(BaseModel):
    id: str
    created_at: datetime


class CounselorDashboardResponse(BaseModel):
    total_students: int
    total_cvs_optimized: int
    total_interviews: int
    avg_score: float | None = None

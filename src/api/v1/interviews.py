"""Mock Interview (F-05, F-06): bat dau phien, tra loi, bao cao STAR, lich su."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.core.security import get_current_user
from src.db.database import get_db
from src.db.models import CV, InterviewQuestion, InterviewReport, InterviewSession, JobDescription, User
from src.models.schemas import (
    InterviewHistoryItem,
    InterviewReportResponse,
    InterviewRespondRequest,
    InterviewRespondResponse,
    InterviewStartRequest,
    InterviewStartResponse,
    InterviewStatusResponse,
    QuestionOut,
    STARCriterionScore,
)
from src.services.interview_service import (
    evaluate_single_answer,
    generate_questions_for_session,
    generate_report_for_session,
)

router = APIRouter(prefix="/interviews", tags=["interviews"])
logger = logging.getLogger(__name__)


def _get_owned_session(session_id: str, current_user: User, db: Session) -> InterviewSession:
    session = db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay phien phong van")
    if session.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Khong co quyen truy cap phien nay")
    return session


@router.post("/start", response_model=InterviewStartResponse, status_code=status.HTTP_201_CREATED)
async def start_interview(
    payload: InterviewStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InterviewStartResponse:
    cv = db.get(CV, payload.cv_id)
    if cv is None or cv.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay CV cua ban")
    jd = db.get(JobDescription, payload.jd_id)
    if jd is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay JD")

    question_texts = await generate_questions_for_session(
        cv_text=cv.raw_text or "",
        cv_parsed_json=cv.parsed_json,
        jd_title=jd.title,
        jd_requirements=jd.requirements_text,
        num_questions=payload.total_questions,
    )

    session = InterviewSession(
        user_id=current_user.id,
        cv_id=cv.id,
        jd_id=jd.id,
        status="ongoing",
        total_questions=len(question_texts),
        current_question_index=0,
    )
    db.add(session)
    db.flush()

    for idx, text in enumerate(question_texts):
        db.add(InterviewQuestion(session_id=session.id, question_index=idx, question_text=text))
    db.commit()
    db.refresh(session)

    first_question = (
        db.query(InterviewQuestion)
        .filter(InterviewQuestion.session_id == session.id, InterviewQuestion.question_index == 0)
        .first()
    )

    return InterviewStartResponse(
        session_id=session.id,
        status=session.status,
        total_questions=session.total_questions,
        current_index=session.current_question_index,
        first_question=QuestionOut(index=0, text=first_question.question_text),
    )


@router.post("/{session_id}/respond", response_model=InterviewRespondResponse)
async def respond_interview(
    session_id: str,
    payload: InterviewRespondRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InterviewRespondResponse:
    session = _get_owned_session(session_id, current_user, db)
    if session.status != "ongoing":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phien phong van da ket thuc")

    question = (
        db.query(InterviewQuestion)
        .filter(
            InterviewQuestion.session_id == session.id,
            InterviewQuestion.question_index == session.current_question_index,
        )
        .first()
    )
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay cau hoi hien tai")

    answering_follow_up = bool(question.follow_up_question) and question.follow_up_answer is None

    evaluation = await evaluate_single_answer(
        question_text=question.follow_up_question if answering_follow_up else question.question_text,
        user_answer=payload.answer,
    )

    if answering_follow_up:
        question.follow_up_answer = payload.answer
    else:
        question.user_answer = payload.answer

    if evaluation.get("star_score") is not None:
        question.star_score_json = evaluation["star_score"]

    needs_follow_up = bool(evaluation.get("needs_follow_up")) and not answering_follow_up
    if needs_follow_up and evaluation.get("follow_up_question"):
        question.follow_up_question = evaluation["follow_up_question"]
        db.commit()
        return InterviewRespondResponse(
            current_index=session.current_question_index,
            is_follow_up=True,
            status=session.status,
            next_question=QuestionOut(index=session.current_question_index, text=question.follow_up_question),
        )

    next_index = session.current_question_index + 1
    if next_index >= session.total_questions:
        session.status = "completed"
        session.current_question_index = next_index
        session.completed_at = datetime.now(timezone.utc)
        db.commit()

        await _create_report(session, db)

        return InterviewRespondResponse(
            current_index=next_index, is_follow_up=False, status=session.status, next_question=None
        )

    session.current_question_index = next_index
    next_question = (
        db.query(InterviewQuestion)
        .filter(InterviewQuestion.session_id == session.id, InterviewQuestion.question_index == next_index)
        .first()
    )
    db.commit()
    return InterviewRespondResponse(
        current_index=next_index,
        is_follow_up=False,
        status=session.status,
        next_question=QuestionOut(index=next_index, text=next_question.question_text) if next_question else None,
    )


async def _create_report(session: InterviewSession, db: Session) -> None:
    """Build QA history from DB questions, invoke LangGraph report agent,
    and persist an InterviewReport row."""
    questions = (
        db.query(InterviewQuestion)
        .filter(InterviewQuestion.session_id == session.id)
        .order_by(InterviewQuestion.question_index)
        .all()
    )
    qa_history: list[dict] = []
    for q in questions:
        entry: dict = {
            "question": q.question_text,
            "answer": q.user_answer or "",
            "star_score": q.star_score_json or {},
        }
        if q.follow_up_question:
            entry["follow_up_question"] = q.follow_up_question
            entry["follow_up_answer"] = q.follow_up_answer or ""
        qa_history.append(entry)

    try:
        report_data = await generate_report_for_session(
            qa_history=qa_history,
            jd_title=session.jd.title if session.jd else "",
        )
    except Exception:
        logger.exception("Failed to generate interview report for session %s", session.id)
        return

    report = InterviewReport(
        session_id=session.id,
        total_score=report_data.get("total_score", 0.0),
        star_scores_json=report_data.get("star_scores"),
        strengths_json=report_data.get("strengths"),
        improvements_json=report_data.get("improvements"),
        recommendations_json=report_data.get("recommendations"),
    )
    db.add(report)
    db.commit()


@router.get("/history", response_model=list[InterviewHistoryItem])
def get_interview_history(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[InterviewHistoryItem]:
    sessions = (
        db.query(InterviewSession)
        .filter(InterviewSession.user_id == current_user.id)
        .order_by(InterviewSession.created_at.desc())
        .all()
    )
    items = []
    for session in sessions:
        report = db.query(InterviewReport).filter(InterviewReport.session_id == session.id).first()
        items.append(
            InterviewHistoryItem(
                session_id=session.id,
                jd_title=session.jd.title if session.jd else "",
                total_score=report.total_score if report else None,
                status=session.status,
                created_at=session.created_at,
            )
        )
    return items


@router.get("/{session_id}", response_model=InterviewStatusResponse)
def get_interview_status(
    session_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> InterviewStatusResponse:
    session = _get_owned_session(session_id, current_user, db)
    return InterviewStatusResponse(
        session_id=session.id,
        status=session.status,
        current_index=session.current_question_index,
        total_questions=session.total_questions,
    )


@router.get("/{session_id}/report", response_model=InterviewReportResponse)
def get_interview_report(
    session_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> InterviewReportResponse:
    session = _get_owned_session(session_id, current_user, db)
    report = db.query(InterviewReport).filter(InterviewReport.session_id == session.id).first()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Bao cao chua san sang (phien chua hoan thanh)"
        )

    star_scores = None
    if report.star_scores_json:
        star_scores = {}
        for key, value in report.star_scores_json.items():
            if isinstance(value, dict):
                star_scores[key] = STARCriterionScore(**value)
            else:
                star_scores[key] = STARCriterionScore(score=float(value), max=25.0)

    return InterviewReportResponse(
        session_id=session.id,
        total_score=report.total_score,
        star_scores=star_scores,
        strengths=report.strengths_json,
        improvements=report.improvements_json,
        recommendations=report.recommendations_json,
    )

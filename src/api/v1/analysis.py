"""Gap Analysis (F-03, F-04): so khop CV vs JD, Accept/Reject goi y toi uu (HITL)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.core.security import get_current_user
from src.db.database import get_db
from src.db.models import CV, CVAnalysis, JobDescription, OptimizationDecision, User
from src.models.schemas import (
    AnalysisHistoryItem,
    GapAnalysisRequest,
    GapAnalysisResponse,
    SuggestionDecisionRequest,
    SuggestionDecisionResponse,
)
from src.services.gap_analysis_service import analyze_cv_against_jd

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _get_owned_analysis(analysis_id: str, current_user: User, db: Session) -> CVAnalysis:
    analysis = db.get(CVAnalysis, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay ket qua phan tich")
    if analysis.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Khong co quyen xem phan tich nay")
    return analysis


def _to_response(analysis: CVAnalysis) -> GapAnalysisResponse:
    return GapAnalysisResponse(
        id=analysis.id,
        cv_id=analysis.cv_id,
        jd_id=analysis.jd_id,
        match_score=analysis.match_score,
        gap_analysis=analysis.gap_analysis_json,
        suggestions=analysis.suggestions_json,
        created_at=analysis.created_at,
    )


@router.post("/gap", response_model=GapAnalysisResponse, status_code=status.HTTP_201_CREATED)
async def start_gap_analysis(
    payload: GapAnalysisRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GapAnalysisResponse:
    cv = db.get(CV, payload.cv_id)
    if cv is None or cv.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay CV cua ban")
    jd = db.get(JobDescription, payload.jd_id)
    if jd is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khong tim thay JD")

    result = await analyze_cv_against_jd(
        cv_raw_text=cv.raw_text or "",
        cv_parsed_json=cv.parsed_json,
        jd_title=jd.title,
        jd_requirements=jd.requirements_text,
        jd_parsed_json=jd.parsed_json,
    )

    analysis = CVAnalysis(
        user_id=current_user.id,
        cv_id=cv.id,
        jd_id=jd.id,
        match_score=result.get("match_score", 0.0),
        gap_analysis_json={
            "matched_skills": result.get("matched_skills", []),
            "partial_skills": result.get("partial_skills", []),
            "missing_skills": result.get("missing_skills", []),
            "gaps": result.get("gaps"),
        },
        suggestions_json=result.get("suggestions"),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return _to_response(analysis)


@router.get("/history", response_model=list[AnalysisHistoryItem])
def get_analysis_history(
    cv_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CVAnalysis]:
    query = db.query(CVAnalysis).filter(CVAnalysis.user_id == current_user.id)
    if cv_id:
        query = query.filter(CVAnalysis.cv_id == cv_id)
    return query.order_by(CVAnalysis.created_at.desc()).all()


@router.get("/{analysis_id}", response_model=GapAnalysisResponse)
def get_analysis(
    analysis_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> GapAnalysisResponse:
    analysis = _get_owned_analysis(analysis_id, current_user, db)
    return _to_response(analysis)


@router.post("/{analysis_id}/decide", response_model=SuggestionDecisionResponse)
def decide_suggestion(
    analysis_id: str,
    payload: SuggestionDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OptimizationDecision:
    analysis = _get_owned_analysis(analysis_id, current_user, db)

    decision = (
        db.query(OptimizationDecision)
        .filter(
            OptimizationDecision.analysis_id == analysis.id,
            OptimizationDecision.suggestion_index == payload.suggestion_index,
        )
        .first()
    )
    if decision is None:
        decision = OptimizationDecision(
            user_id=current_user.id,
            cv_id=analysis.cv_id,
            analysis_id=analysis.id,
            suggestion_index=payload.suggestion_index,
            accepted=payload.accepted,
        )
        db.add(decision)

    # HITL (Human-in-the-Loop): SV la nguoi quyet dinh cuoi cung. He thong
    # KHONG BAO GIO tu dong sua CV — chi luu lai lua chon Accept/Reject cua
    # SV cho tung goi y, va noi dung cuoi (final_text) neu SV co chinh sua.
    decision.accepted = payload.accepted
    decision.final_text = payload.final_text
    db.commit()
    db.refresh(decision)
    return decision

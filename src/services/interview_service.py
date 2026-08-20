"""Interview Service — high-level facade + session management for the
Mock Interview Agent.

This is the function set the API layer (owned by agent_web, in `src/api/`)
should call from the `/api/v1/interviews/*` endpoints. It hides the
LangGraph plumbing behind plain input-in/dict-out functions and tracks
per-session progress (current question index, chat history) in memory.

WHY in-memory sessions instead of the `interview_sessions` /
`interview_questions` DB tables from system_architecture.md §3.3.6-3.3.7?
Those tables (and the SQLAlchemy models to read/write them) belong to
agent_web (`src/db/`, `src/models/` are outside this agent's scope — see
CLAUDE.md). `InterviewSessionStore` below lets the full interview flow run
and be unit-tested today; swapping it for DB-backed persistence later only
means re-implementing this class's `save`/`get` against the database — the
LLM logic in `src/agents/interview/nodes.py` never touches this class
directly, so nothing else needs to change.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from src.agents.interview.graph import create_interview_graph

# Compiled once and reused — see the equivalent comment in
# gap_analysis_service.py for why this is safe (the graph itself is
# stateless; all per-run data lives in the state dict passed to `.ainvoke`).
_interview_graph = create_interview_graph()


@dataclass
class InterviewSession:
    session_id: str
    cv_text: str
    jd_title: str
    jd_requirements: str
    questions: list[str]
    current_index: int = 0
    qa_history: list[dict[str, Any]] = field(default_factory=list)
    status: str = "ongoing"  # ongoing | completed
    pending_follow_up: str | None = None
    report: dict[str, Any] | None = None


class InterviewSessionStore:
    """In-memory session store — see module docstring for the DB caveat."""

    def __init__(self) -> None:
        self._sessions: dict[str, InterviewSession] = {}

    def save(self, session: InterviewSession) -> None:
        self._sessions[session.session_id] = session

    def get(self, session_id: str) -> InterviewSession:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise KeyError(f"Interview session '{session_id}' not found.") from None


_store = InterviewSessionStore()


async def start_interview(
    *,
    cv_text: str,
    cv_parsed_json: dict[str, Any] | None = None,
    jd_title: str,
    jd_requirements: str,
    num_questions: int = 5,
) -> dict[str, Any]:
    """Start a new mock interview session.

    Returns `{session_id, status, total_questions, current_index, question}`.
    Raises ValueError if the input is unusable (see
    src/agents/interview/nodes.py:validate_input).
    """
    result_state = await _interview_graph.ainvoke(
        {
            "operation": "start",
            "cv_text": cv_text,
            "cv_parsed_json": cv_parsed_json or {},
            "jd_title": jd_title,
            "jd_requirements": jd_requirements,
            "num_questions": num_questions,
        }
    )
    if result_state.get("error"):
        raise ValueError(result_state["error"])

    questions = result_state["interview_questions"]
    session = InterviewSession(
        session_id=str(uuid.uuid4()),
        cv_text=cv_text,
        jd_title=jd_title,
        jd_requirements=jd_requirements,
        questions=questions,
    )
    _store.save(session)
    return {
        "session_id": session.session_id,
        "status": session.status,
        "total_questions": len(questions),
        "current_index": 0,
        "question": questions[0],
    }


async def submit_answer(*, session_id: str, answer: str) -> dict[str, Any]:
    """Submit an answer for the current question (or a pending follow-up).

    Returns the next question to ask, or a follow-up question for the same
    turn (`is_follow_up: True`), or `question: None` with `status:
    "completed"` once every question has been answered.
    """
    session = _store.get(session_id)
    if session.status == "completed":
        raise ValueError("This interview session is already completed.")

    is_follow_up = session.pending_follow_up is not None
    question_text = session.pending_follow_up or session.questions[session.current_index]

    result_state = await _interview_graph.ainvoke(
        {"operation": "respond", "question_text": question_text, "user_answer": answer}
    )
    if result_state.get("error"):
        raise ValueError(result_state["error"])

    star_score = result_state["star_score"]
    follow_up_question = result_state.get("follow_up_question")

    if is_follow_up:
        # This answer was to a follow-up on the current question: attach it
        # to the history entry already created for that question, and
        # average the two STAR scorings so a good follow-up answer can
        # still lift the recorded score for this turn.
        current_entry = session.qa_history[-1]
        current_entry["follow_up_answer"] = answer
        current_entry["star_score"] = {
            component: round((current_entry["star_score"][component] + star_score[component]) / 2, 2)
            for component in star_score
        }
        session.pending_follow_up = None
    else:
        entry: dict[str, Any] = {"question": question_text, "answer": answer, "star_score": star_score}
        if follow_up_question:
            entry["follow_up_question"] = follow_up_question
        session.qa_history.append(entry)
        session.pending_follow_up = follow_up_question or None

    if session.pending_follow_up:
        _store.save(session)
        return {
            "session_id": session.session_id,
            "status": session.status,
            "is_follow_up": True,
            "current_index": session.current_index,
            "question": session.pending_follow_up,
        }

    session.current_index += 1
    if session.current_index >= len(session.questions):
        session.status = "completed"
        _store.save(session)
        return {
            "session_id": session.session_id,
            "status": session.status,
            "is_follow_up": False,
            "current_index": session.current_index,
            "question": None,
        }

    _store.save(session)
    return {
        "session_id": session.session_id,
        "status": session.status,
        "is_follow_up": False,
        "current_index": session.current_index,
        "question": session.questions[session.current_index],
    }


async def get_report(session_id: str) -> dict[str, Any]:
    """Build (and cache) the final STAR report for a completed session.

    Raises ValueError if the session isn't completed yet.
    """
    session = _store.get(session_id)
    if session.status != "completed":
        raise ValueError("Cannot generate a report until the interview session is completed.")
    if session.report is not None:
        return session.report

    result_state = await _interview_graph.ainvoke(
        {"operation": "report", "qa_history": session.qa_history, "jd_title": session.jd_title}
    )
    if result_state.get("error"):
        raise ValueError(result_state["error"])

    session.report = result_state["final_report"]
    _store.save(session)
    return session.report


def get_session_state(session_id: str) -> dict[str, Any]:
    """Read-only snapshot of a session's current progress."""
    session = _store.get(session_id)
    return {
        "session_id": session.session_id,
        "status": session.status,
        "total_questions": len(session.questions),
        "current_index": session.current_index,
        "qa_history": session.qa_history,
    }


# -------------------------------------------------------------------------
# Thin graph-only wrappers — used by the DB-backed API routes in
# src/api/v1/interviews.py. These call the LangGraph agent without
# touching the in-memory InterviewSessionStore above.
# -------------------------------------------------------------------------


async def generate_questions_for_session(
    *,
    cv_text: str,
    cv_parsed_json: dict[str, Any] | None = None,
    jd_title: str,
    jd_requirements: str,
    num_questions: int = 5,
) -> list[str]:
    """Generate interview questions via the LangGraph agent."""
    result_state = await _interview_graph.ainvoke(
        {
            "operation": "start",
            "cv_text": cv_text,
            "cv_parsed_json": cv_parsed_json or {},
            "jd_title": jd_title,
            "jd_requirements": jd_requirements,
            "num_questions": num_questions,
        }
    )
    if result_state.get("error"):
        raise ValueError(result_state["error"])
    return result_state["interview_questions"]


async def evaluate_single_answer(
    *,
    question_text: str,
    user_answer: str,
) -> dict[str, Any]:
    """Evaluate one answer via the LangGraph agent.

    Returns {star_score, needs_follow_up, follow_up_question, feedback}.
    """
    result_state = await _interview_graph.ainvoke(
        {
            "operation": "respond",
            "question_text": question_text,
            "user_answer": user_answer,
        }
    )
    if result_state.get("error"):
        raise ValueError(result_state["error"])
    evaluation = result_state.get("evaluation", {})
    return {
        "star_score": result_state.get("star_score"),
        "needs_follow_up": evaluation.get("needs_follow_up", False),
        "follow_up_question": result_state.get("follow_up_question"),
        "feedback": evaluation.get("feedback", ""),
    }


async def generate_report_for_session(
    *,
    qa_history: list[dict[str, Any]],
    jd_title: str,
) -> dict[str, Any]:
    """Generate final STAR report via the LangGraph agent.

    Returns {total_score, star_scores, strengths, improvements, recommendations}.
    """
    result_state = await _interview_graph.ainvoke(
        {
            "operation": "report",
            "qa_history": qa_history,
            "jd_title": jd_title,
        }
    )
    if result_state.get("error"):
        raise ValueError(result_state["error"])
    return result_state["final_report"]

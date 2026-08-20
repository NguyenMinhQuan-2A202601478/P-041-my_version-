"""LangGraph nodes for the Mock Interview Agent.

Graph routing (see graph.py) branches on `state["operation"]`:
  - "start"   -> generate_questions -> END
  - "respond" -> evaluate_response -> score_star -> [generate_followup?] -> END
  - "report"  -> generate_report -> END

WHY does `score_star` exist as a separate deterministic node instead of
just trusting the LLM's classification directly as the score? Per
CLAUDE.md and the architecture doc: "Diem tinh bang cong thuc, khong phai
LLM" (the score is computed by formula, not decided by the LLM). The LLM
only classifies HOW WELL each STAR component was covered (a qualitative
judgment it's good at); converting that classification into a 0-25 number
per component is a fixed, auditable formula so the same classification
always produces the same score.
"""

from __future__ import annotations

import logging
from statistics import mean
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.agents.interview.prompts import (
    FOLLOW_UP_SYSTEM_PROMPT,
    QUESTION_GENERATION_SYSTEM_PROMPT,
    REPORT_SYSTEM_PROMPT,
    STAR_EVALUATION_SYSTEM_PROMPT,
)
from src.agents.state import InterviewAgentState
from src.services.llm import get_llm

logger = logging.getLogger(__name__)

MIN_QUESTIONS = 5
MAX_QUESTIONS = 7
MAX_SCORE_PER_COMPONENT = 25.0

# Coverage label -> fraction of MAX_SCORE_PER_COMPONENT awarded. This table
# IS the "formula" from system_architecture.md §5.4 — keep it in sync with
# that doc if it ever changes.
_COVERAGE_FACTOR: dict[str, float] = {
    "FULL": 1.00,
    "PARTIAL_STRONG": 0.75,
    "PARTIAL": 0.50,
    "PARTIAL_WEAK": 0.25,
    "NOT_DEMONSTRATED": 0.00,
}

_STAR_COMPONENTS = ("situation", "task", "action", "result")

# Used only if the LLM call fails — keeps the interview usable (degraded,
# generic questions) instead of hard-failing the whole session.
_FALLBACK_QUESTION_POOL = [
    "Hãy giới thiệu ngắn gọn về bản thân và lý do bạn ứng tuyển vị trí {jd_title}.",
    "Hãy kể về một dự án trong CV mà bạn tự hào nhất và vai trò cụ thể của bạn trong đó.",
    "Mô tả một tình huống kỹ thuật khó bạn từng gặp: nhiệm vụ, hành động bạn thực hiện, và kết quả.",
    "Khi bất đồng quan điểm với một thành viên trong nhóm, bạn đã xử lý thế nào?",
    "Bạn đã học một công nghệ mới như thế nào để hoàn thành một công việc cụ thể?",
    "Bạn ưu tiên công việc ra sao khi có nhiều nhiệm vụ cùng thời hạn?",
    "Mục tiêu phát triển nghề nghiệp của bạn trong hai năm tới là gì?",
]


# --------------------------------------------------------------------------
# Structured output schemas
# --------------------------------------------------------------------------
class _QuestionList(BaseModel):
    questions: list[str] = Field(default_factory=list)


CoverageLabel = Literal["FULL", "PARTIAL_STRONG", "PARTIAL", "PARTIAL_WEAK", "NOT_DEMONSTRATED"]


class _StarCoverage(BaseModel):
    situation: CoverageLabel
    task: CoverageLabel
    action: CoverageLabel
    result: CoverageLabel
    needs_follow_up: bool
    weakest_component: Literal["situation", "task", "action", "result"]
    feedback: str = Field(default="")


class _ReportNarrative(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# validate_input
# --------------------------------------------------------------------------
async def validate_input(state: InterviewAgentState) -> dict[str, Any]:
    operation = state.get("operation")
    if operation == "start":
        if not (state.get("cv_text") or "").strip():
            return {"error": "CV has no content to generate interview questions from."}
        if not (state.get("jd_title") or "").strip() or not (state.get("jd_requirements") or "").strip():
            return {"error": "The job description is missing a title or requirements text."}
        count = int(state.get("num_questions") or MIN_QUESTIONS)
        if not MIN_QUESTIONS <= count <= MAX_QUESTIONS:
            return {"error": f"num_questions must be between {MIN_QUESTIONS} and {MAX_QUESTIONS}."}
    elif operation == "respond":
        if not (state.get("question_text") or "").strip():
            return {"error": "Missing the question being answered."}
        if len((state.get("user_answer") or "").strip()) < 2:
            return {"error": "The answer is too short to evaluate."}
    elif operation == "report":
        if not state.get("qa_history"):
            return {"error": "No question/answer history to build a report from."}
    else:
        return {"error": f"Unknown Interview Agent operation: {operation!r}."}
    return {"error": ""}


# --------------------------------------------------------------------------
# generate_questions
# --------------------------------------------------------------------------
def _fallback_questions(jd_title: str, count: int) -> list[str]:
    pool = [q.format(jd_title=jd_title) for q in _FALLBACK_QUESTION_POOL]
    return pool[:count]


def _guard_and_dedupe_questions(questions: list[str], count: int, jd_title: str) -> list[str]:
    """Enforce a minimum length and drop duplicates, then top up from the
    fallback pool if the LLM returned fewer usable questions than needed.
    This is the "guard_questions" safety net from system_architecture.md,
    folded into generate_questions since it's a lightweight post-check
    rather than a separate LLM call."""
    seen: set[str] = set()
    cleaned: list[str] = []
    for question in questions:
        normalized = " ".join(str(question).split())
        key = normalized.casefold()
        if len(normalized) >= 15 and key not in seen:
            cleaned.append(normalized)
            seen.add(key)
    for fallback in _fallback_questions(jd_title, count):
        if len(cleaned) >= count:
            break
        if fallback.casefold() not in seen:
            cleaned.append(fallback)
            seen.add(fallback.casefold())
    return cleaned[:count]


async def generate_questions(state: InterviewAgentState) -> dict[str, Any]:
    count = int(state.get("num_questions") or MIN_QUESTIONS)
    llm = get_llm()
    structured_llm = llm.with_structured_output(_QuestionList)
    messages = [
        SystemMessage(content=QUESTION_GENERATION_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Generate exactly {count} interview questions.\n\n"
                f"Target job title: {state['jd_title']}\n\n"
                f"Job description:\n{state['jd_requirements']}\n\n"
                f"Candidate CV:\n{state['cv_text']}"
            )
        ),
    ]
    try:
        result = await structured_llm.ainvoke(messages)
        raw_questions = result.questions if isinstance(result, _QuestionList) else []
    except Exception as exc:
        logger.warning("generate_questions: LLM call failed, using fallback pool: %s", exc)
        raw_questions = []

    questions = _guard_and_dedupe_questions(raw_questions, count, state["jd_title"])
    return {"interview_questions": questions}


# --------------------------------------------------------------------------
# evaluate_response
# --------------------------------------------------------------------------
def _fallback_star_coverage(answer: str) -> _StarCoverage:
    """Very rough keyword-based fallback used only if the LLM call fails —
    keeps the interview usable in degraded mode rather than crashing."""
    lowered = answer.casefold()
    word_count = len(answer.split())
    cue_words = {
        "situation": ("khi ", "bối cảnh", "tình huống", "lúc đó", "situation", "context"),
        "task": ("nhiệm vụ", "mục tiêu", "trách nhiệm", "task", "goal", "responsible"),
        "action": ("tôi đã", "tôi thực hiện", "i did", "i built", "i implemented", "i designed"),
        "result": ("kết quả", "đạt được", "cải thiện", "%", "result", "achieved", "improved"),
    }
    coverage: dict[str, str] = {}
    for component, cues in cue_words.items():
        has_cue = any(cue in lowered for cue in cues)
        if has_cue and word_count >= 40:
            coverage[component] = "PARTIAL_STRONG"
        elif has_cue:
            coverage[component] = "PARTIAL"
        elif word_count >= 20:
            coverage[component] = "PARTIAL_WEAK"
        else:
            coverage[component] = "NOT_DEMONSTRATED"
    weakest = min(coverage, key=lambda k: _COVERAGE_FACTOR[coverage[k]])
    return _StarCoverage(
        situation=coverage["situation"],
        task=coverage["task"],
        action=coverage["action"],
        result=coverage["result"],
        needs_follow_up=_COVERAGE_FACTOR[coverage[weakest]] < 0.75,
        weakest_component=weakest,
        feedback=f"The '{weakest}' component of your answer could use more detail.",
    )


async def evaluate_response(state: InterviewAgentState) -> dict[str, Any]:
    llm = get_llm()
    structured_llm = llm.with_structured_output(_StarCoverage)
    messages = [
        SystemMessage(content=STAR_EVALUATION_SYSTEM_PROMPT),
        HumanMessage(content=f"Question: {state['question_text']}\n\nCandidate's answer: {state['user_answer']}"),
    ]
    try:
        result = await structured_llm.ainvoke(messages)
        coverage = result if isinstance(result, _StarCoverage) else _StarCoverage.model_validate(result)
    except Exception as exc:
        logger.warning("evaluate_response: LLM call failed, using fallback heuristic: %s", exc)
        coverage = _fallback_star_coverage(state["user_answer"])

    return {"evaluation": coverage.model_dump()}


# --------------------------------------------------------------------------
# score_star (deterministic — see module docstring)
# --------------------------------------------------------------------------
async def score_star(state: InterviewAgentState) -> dict[str, Any]:
    evaluation = state.get("evaluation", {})
    star_score = {
        component: round(
            _COVERAGE_FACTOR.get(evaluation.get(component, "NOT_DEMONSTRATED"), 0.0) * MAX_SCORE_PER_COMPONENT, 2
        )
        for component in _STAR_COMPONENTS
    }
    return {"star_score": star_score}


# --------------------------------------------------------------------------
# generate_followup (conditional — only runs when evaluate_response flagged
# needs_follow_up; routed in graph.py)
# --------------------------------------------------------------------------
async def generate_followup(state: InterviewAgentState) -> dict[str, Any]:
    evaluation = state.get("evaluation", {})
    weakest = evaluation.get("weakest_component", "result")
    llm = get_llm()
    messages = [
        SystemMessage(content=FOLLOW_UP_SYSTEM_PROMPT.format(weakest_component=weakest)),
        HumanMessage(content=f"Question: {state['question_text']}\n\nCandidate's answer: {state['user_answer']}"),
    ]
    try:
        response = await llm.ainvoke(messages)
        follow_up = str(response.content).strip()
    except Exception as exc:
        logger.warning("generate_followup: LLM call failed, using generic fallback: %s", exc)
        generic_fallback = {
            "situation": "Bạn có thể mô tả rõ hơn bối cảnh lúc đó không?",
            "task": "Nhiệm vụ hoặc mục tiêu cụ thể của bạn trong tình huống đó là gì?",
            "action": "Bạn đã trực tiếp thực hiện những hành động nào?",
            "result": "Kết quả cụ thể là gì? Bạn có số liệu hoặc bằng chứng nào không?",
        }
        follow_up = generic_fallback.get(weakest, generic_fallback["result"])

    return {"follow_up_question": follow_up or ""}


# --------------------------------------------------------------------------
# generate_report
# --------------------------------------------------------------------------
def _compute_final_scores(qa_history: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministically average per-question STAR scores into the final
    report numbers. Kept separate from the LLM call so the numbers in the
    report can never be silently altered by the model."""
    score_sets = [entry.get("star_score", {}) for entry in qa_history if entry.get("star_score")]
    if not score_sets:
        star_scores = dict.fromkeys(_STAR_COMPONENTS, 0.0)
    else:
        star_scores = {
            component: round(mean(float(scores.get(component, 0.0)) for scores in score_sets), 2)
            for component in _STAR_COMPONENTS
        }
    total_score = round(sum(star_scores.values()), 2)  # out of 100 (4 components x 25 max each)
    return {"total_score": total_score, "star_scores": star_scores}


async def generate_report(state: InterviewAgentState) -> dict[str, Any]:
    qa_history = state.get("qa_history", [])
    computed = _compute_final_scores(qa_history)

    llm = get_llm()
    structured_llm = llm.with_structured_output(_ReportNarrative)
    transcript_lines = []
    for index, entry in enumerate(qa_history, start=1):
        transcript_lines.append(f"Q{index}: {entry.get('question', '')}\nA{index}: {entry.get('answer', '')}")
        if entry.get("follow_up_question"):
            transcript_lines.append(
                f"Follow-up: {entry['follow_up_question']}\nFollow-up answer: {entry.get('follow_up_answer', '')}"
            )
    transcript = "\n\n".join(transcript_lines)

    messages = [
        SystemMessage(content=REPORT_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Target job title: {state.get('jd_title', '')}\n\n"
                f"Transcript:\n{transcript}\n\n"
                f"Already-calculated STAR scores (context only, do not change): {computed['star_scores']}\n"
                f"Already-calculated total score (context only, do not change): {computed['total_score']}"
            )
        ),
    ]
    try:
        result = await structured_llm.ainvoke(messages)
        narrative = result if isinstance(result, _ReportNarrative) else _ReportNarrative.model_validate(result)
    except Exception as exc:
        logger.warning("generate_report: LLM call failed, using generic narrative: %s", exc)
        weakest = min(computed["star_scores"], key=computed["star_scores"].get)
        narrative = _ReportNarrative(
            strengths=["Bạn đã hoàn thành đầy đủ các câu hỏi phỏng vấn."],
            improvements=[f"Nên làm rõ hơn phần '{weakest}' trong các câu trả lời."],
            recommendations=["Trả lời theo cấu trúc STAR: Bối cảnh → Nhiệm vụ → Hành động → Kết quả có số liệu."],
        )

    star_scores_nested = {
        component: {
            "score": score,
            "max": MAX_SCORE_PER_COMPONENT,
            "feedback": None,
        }
        for component, score in computed["star_scores"].items()
    }
    final_report = {
        "total_score": computed["total_score"],
        "star_scores": star_scores_nested,
        "strengths": narrative.strengths,
        "improvements": narrative.improvements,
        "recommendations": narrative.recommendations,
    }
    return {"final_report": final_report}

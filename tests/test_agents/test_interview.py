"""Tests for the Mock Interview Agent (src/agents/interview/).

Like test_gap_analysis.py, these tests exercise the deterministic pieces
directly (no LLM): `score_star` (the formula from system_architecture.md
§5.4), `validate_input`'s guard rails, the routing helpers in graph.py, and
graph compilation. No network/LLM mocking is needed for any of these because
none of them call `get_llm()`.
"""

from __future__ import annotations

import pytest

from src.agents.interview.graph import _route_after_scoring, _route_operation, create_interview_graph
from src.agents.interview.nodes import (
    MAX_QUESTIONS,
    MIN_QUESTIONS,
    _guard_and_dedupe_questions,
    score_star,
    validate_input,
)
from src.models.schemas import InterviewStartRequest


# ---------------------------------------------------------------------------
# score_star — deterministic formula (must match the worked example in
# docs/architecture/system_architecture.md §5.4 exactly: 25 + 12.5 + 18.75 +
# 0 = 56.25/100)
# ---------------------------------------------------------------------------
async def test_score_star_matches_architecture_doc_example():
    state = {
        "evaluation": {
            "situation": "FULL",
            "task": "PARTIAL",
            "action": "PARTIAL_STRONG",
            "result": "NOT_DEMONSTRATED",
        }
    }

    result = await score_star(state)

    star_score = result["star_score"]
    assert star_score == {"situation": 25.0, "task": 12.5, "action": 18.75, "result": 0.0}
    assert sum(star_score.values()) == 56.25


async def test_score_star_full_coverage_on_every_component_is_100():
    state = {"evaluation": {"situation": "FULL", "task": "FULL", "action": "FULL", "result": "FULL"}}

    result = await score_star(state)

    assert sum(result["star_score"].values()) == 100.0


async def test_score_star_missing_evaluation_defaults_to_zero():
    result = await score_star({"evaluation": {}})
    assert result["star_score"] == {"situation": 0.0, "task": 0.0, "action": 0.0, "result": 0.0}


# ---------------------------------------------------------------------------
# validate_input — per-operation guard rails
# ---------------------------------------------------------------------------
async def test_validate_input_start_with_valid_data_has_no_error():
    state = {
        "operation": "start",
        "cv_text": "Nguyen Van A - Python developer.",
        "jd_title": "Backend Developer",
        "jd_requirements": "Yeu cau Python, FastAPI.",
        "num_questions": 5,
    }

    result = await validate_input(state)

    assert result["error"] == ""


async def test_validate_input_start_missing_cv_returns_error():
    state = {
        "operation": "start",
        "cv_text": "",
        "jd_title": "Backend Developer",
        "jd_requirements": "Yeu cau Python.",
        "num_questions": 5,
    }

    result = await validate_input(state)

    assert result["error"]


@pytest.mark.parametrize("count", [1, 4, 8, 10])
async def test_validate_input_start_rejects_question_count_outside_5_to_7(count):
    state = {
        "operation": "start",
        "cv_text": "Nguyen Van A - Python developer.",
        "jd_title": "Backend Developer",
        "jd_requirements": "Yeu cau Python.",
        "num_questions": count,
    }

    result = await validate_input(state)

    assert result["error"]
    assert "5" in result["error"] and "7" in result["error"]


@pytest.mark.parametrize("count", [5, 6, 7])
async def test_validate_input_start_accepts_question_count_in_5_to_7(count):
    state = {
        "operation": "start",
        "cv_text": "Nguyen Van A - Python developer.",
        "jd_title": "Backend Developer",
        "jd_requirements": "Yeu cau Python.",
        "num_questions": count,
    }

    result = await validate_input(state)

    assert result["error"] == ""


async def test_validate_input_respond_with_too_short_answer_returns_error():
    # validate_input requires len(answer.strip()) >= 2 — a single character
    # (or whitespace-only) answer must be rejected as "too short to evaluate".
    state = {"operation": "respond", "question_text": "Ban hay ke ve mot du an?", "user_answer": "K"}
    result = await validate_input(state)
    assert result["error"]


async def test_validate_input_respond_with_sufficient_answer_has_no_error():
    state = {
        "operation": "respond",
        "question_text": "Ban hay ke ve mot du an?",
        "user_answer": "Toi da xay dung mot he thong quan ly noi bo.",
    }
    result = await validate_input(state)
    assert result["error"] == ""


async def test_validate_input_report_without_history_returns_error():
    result = await validate_input({"operation": "report", "qa_history": []})
    assert result["error"]


async def test_validate_input_unknown_operation_returns_error():
    result = await validate_input({"operation": "not-a-real-operation"})
    assert result["error"]


# ---------------------------------------------------------------------------
# num_questions defaults to the 5-7 range (F-05 acceptance criterion)
# ---------------------------------------------------------------------------
def test_min_max_questions_constants_match_prd_range():
    assert MIN_QUESTIONS == 5
    assert MAX_QUESTIONS == 7


def test_interview_start_request_defaults_to_5_questions():
    request = InterviewStartRequest(cv_id="cv-1", jd_id="jd-1")
    assert request.total_questions == 5


@pytest.mark.parametrize("value", [4, 8, 0, -1])
def test_interview_start_request_rejects_out_of_range_total_questions(value):
    with pytest.raises(Exception):  # pydantic.ValidationError
        InterviewStartRequest(cv_id="cv-1", jd_id="jd-1", total_questions=value)


@pytest.mark.parametrize("value", [5, 6, 7])
def test_interview_start_request_accepts_in_range_total_questions(value):
    request = InterviewStartRequest(cv_id="cv-1", jd_id="jd-1", total_questions=value)
    assert request.total_questions == value


def test_guard_and_dedupe_questions_tops_up_from_fallback_pool():
    """If the LLM returns fewer usable questions than requested, the guard
    should top up from the fallback pool rather than under-deliver."""
    too_few = ["Short", "Also too short"]  # both under the 15-char minimum

    result = _guard_and_dedupe_questions(too_few, count=5, jd_title="Backend Developer")

    assert len(result) == 5
    assert len(set(result)) == 5  # no duplicates


def test_guard_and_dedupe_questions_drops_duplicates():
    duplicated = [
        "Hay ke ve mot du an ban tu hao nhat.",
        "Hay ke ve mot du an ban tu hao nhat.",
        "Ban da hoc cong nghe moi nhu the nao de hoan thanh cong viec?",
    ]

    result = _guard_and_dedupe_questions(duplicated, count=5, jd_title="Backend Developer")

    assert len(result) == len(set(q.casefold() for q in result))


# ---------------------------------------------------------------------------
# Graph compilation + operation routing
# ---------------------------------------------------------------------------
def test_interview_graph_compiles_without_error():
    graph = create_interview_graph()
    assert graph is not None
    assert "generate_report" in graph.nodes
    assert "generate_followup" in graph.nodes


@pytest.mark.parametrize(
    "operation,expected_node",
    [
        ("start", "generate_questions"),
        ("respond", "evaluate_response"),
        ("report", "generate_report"),
    ],
)
def test_route_operation_dispatches_to_the_right_node(operation, expected_node):
    assert _route_operation({"operation": operation}) == expected_node


def test_route_operation_short_circuits_to_end_on_error():
    from langgraph.graph import END

    assert _route_operation({"operation": "start", "error": "bad input"}) == END


def test_route_after_scoring_goes_to_followup_when_needed():
    assert _route_after_scoring({"evaluation": {"needs_follow_up": True}}) == "generate_followup"


def test_route_after_scoring_ends_when_not_needed():
    from langgraph.graph import END

    assert _route_after_scoring({"evaluation": {"needs_follow_up": False}}) == END

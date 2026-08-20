"""Tests for the CV Gap Analysis Agent (src/agents/gap_analysis/).

These tests call the deterministic nodes directly with hand-built state
dicts — no LLM involved, per the QA task's "mock the LLM / test what's
deterministic" guidance. `compute_match` and `guardrail_check` are exactly
the two nodes the architecture doc calls out as deterministic-by-design
(never delegated to the LLM), which makes them safe and meaningful to test
this way without any mocking.

`pytest.ini` sets `asyncio_mode = auto`, so `async def test_...` functions
run without needing an explicit `@pytest.mark.asyncio` decorator.
"""

from __future__ import annotations

from src.agents.gap_analysis.graph import create_gap_analysis_graph
from src.agents.gap_analysis.nodes import compute_match, guardrail_check, validate_input


# ---------------------------------------------------------------------------
# compute_match — deterministic scoring
# ---------------------------------------------------------------------------
async def test_compute_match_exact_matches_and_a_missing_skill():
    state = {
        "cv_skills": {"skills": ["Python", "FastAPI"]},
        "cv_raw_text": "Toi da lam viec voi Python va FastAPI trong 2 nam.",
        "jd_requirements_extracted": {
            "required_skills": ["Python", "FastAPI"],
            "preferred_skills": ["Docker"],
        },
    }

    result = await compute_match(state)

    assert result["matched_skills"] == ["Python", "FastAPI"]
    assert result["missing_skills"] == ["Docker"]
    assert result["partial_skills"] == []
    # max_points = 2*2.0 (required) + 1*1.0 (preferred) = 5.0
    # earned = 2.0 + 2.0 (both required matched) + 0 (preferred missing) = 4.0
    assert result["match_score"] == 80.0


async def test_compute_match_detects_partial_skill_via_substring():
    state = {
        "cv_skills": {"skills": ["Postgres"]},
        "cv_raw_text": "Toi da dung Postgres cho du an ca nhan.",
        "jd_requirements_extracted": {
            "required_skills": ["PostgreSQL"],
            "preferred_skills": [],
        },
    }

    result = await compute_match(state)

    assert result["matched_skills"] == []
    assert result["partial_skills"] == ["PostgreSQL"]
    assert result["missing_skills"] == []
    # earned = required_weight(2.0) * partial_credit(0.5) = 1.0 out of max 2.0
    assert result["match_score"] == 50.0


async def test_compute_match_no_requirements_yields_zero_score():
    state = {
        "cv_skills": {"skills": ["Python"]},
        "cv_raw_text": "Python developer.",
        "jd_requirements_extracted": {"required_skills": [], "preferred_skills": []},
    }

    result = await compute_match(state)

    assert result["match_score"] == 0.0
    assert result["matched_skills"] == []
    assert result["missing_skills"] == []


async def test_compute_match_falls_back_to_raw_text_when_skill_missing_from_list():
    """A skill absent from cv_skills['skills'] but genuinely written in the
    raw CV text (e.g. inside a project description) should still count as
    matched — this is the whole-word fallback search in `_skill_present`."""
    state = {
        "cv_skills": {"skills": []},
        "cv_raw_text": "Du an ca nhan su dung Docker de dong goi ung dung.",
        "jd_requirements_extracted": {"required_skills": ["Docker"], "preferred_skills": []},
    }

    result = await compute_match(state)

    assert result["matched_skills"] == ["Docker"]
    assert result["match_score"] == 100.0


# ---------------------------------------------------------------------------
# guardrail_check — anti-hallucination gate (CLAUDE.md constraint 1: "Liem
# chinh"; system_architecture.md 5.2 "Anti-Hallucination Guardrails")
# ---------------------------------------------------------------------------
CV_TEXT = (
    "Toi da xay dung REST API cho he thong quan ly noi bo su dung FastAPI va PostgreSQL. "
    "Toi cung ho tro van hanh he thong hang ngay."
)


async def test_guardrail_check_keeps_suggestion_with_verbatim_original_text():
    state = {
        "cv_raw_text": CV_TEXT,
        "missing_skills": ["Docker"],
        "draft_suggestions": [
            {
                "section": "experience",
                "original_text": "xay dung REST API cho he thong quan ly noi bo",
                "suggested_text": "Thiet ke va xay dung REST API cho he thong quan ly noi bo su dung FastAPI",
                "reason": "Lam ro cong nghe da dung",
            }
        ],
    }

    result = await guardrail_check(state)

    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["status"] == "pending"
    assert result["guardrail_notes"] == []


async def test_guardrail_check_rejects_suggestion_introducing_fabricated_skill():
    state = {
        "cv_raw_text": CV_TEXT,
        "missing_skills": ["Docker"],
        "draft_suggestions": [
            {
                "original_text": "xay dung REST API cho he thong quan ly noi bo",
                "suggested_text": "Xay dung REST API va trien khai voi Docker cho he thong quan ly noi bo",
                "reason": "...",
            }
        ],
    }

    result = await guardrail_check(state)

    assert result["suggestions"] == []
    assert len(result["guardrail_notes"]) == 1
    assert "Docker" in result["guardrail_notes"][0]


async def test_guardrail_check_rejects_suggestion_with_fabricated_metric():
    state = {
        "cv_raw_text": CV_TEXT,
        "missing_skills": [],
        "draft_suggestions": [
            {
                "original_text": "xay dung REST API cho he thong quan ly noi bo",
                "suggested_text": "Xay dung REST API giup tang 50% hieu suat cho he thong quan ly noi bo",
                "reason": "...",
            }
        ],
    }

    result = await guardrail_check(state)

    assert result["suggestions"] == []
    assert "number/metric" in result["guardrail_notes"][0]


async def test_guardrail_check_rejects_non_verbatim_original_text():
    state = {
        "cv_raw_text": CV_TEXT,
        "missing_skills": [],
        "draft_suggestions": [
            {
                "original_text": "Toi da lam viec tai NASA nam 2020",
                "suggested_text": "Lam viec tai NASA voi vai tro ky su",
                "reason": "...",
            }
        ],
    }

    result = await guardrail_check(state)

    assert result["suggestions"] == []
    assert "verbatim quote" in result["guardrail_notes"][0]


async def test_guardrail_check_allows_a_number_that_was_already_in_the_original():
    """A number that was already present in the quoted original text is not
    a fabricated metric — only NEW numbers should be rejected."""
    state = {
        "cv_raw_text": "Toi da phuc vu 500 nguoi dung moi ngay cho he thong noi bo.",
        "missing_skills": [],
        "draft_suggestions": [
            {
                "original_text": "phuc vu 500 nguoi dung moi ngay",
                "suggested_text": "Phuc vu 500 nguoi dung moi ngay voi do tin cay cao",
                "reason": "...",
            }
        ],
    }

    result = await guardrail_check(state)

    assert len(result["suggestions"]) == 1


# ---------------------------------------------------------------------------
# validate_input
# ---------------------------------------------------------------------------
async def test_validate_input_with_empty_cv_returns_error():
    state = {"cv_raw_text": "   ", "jd_title": "Backend Developer", "jd_requirements": "Python, FastAPI"}

    result = await validate_input(state)

    assert result["error"]


async def test_validate_input_missing_jd_fields_returns_error():
    state = {"cv_raw_text": "Some CV text", "jd_title": "", "jd_requirements": ""}

    result = await validate_input(state)

    assert result["error"]


async def test_validate_input_with_valid_data_returns_no_error():
    state = {
        "cv_raw_text": "Nguyen Van A - Python developer.",
        "jd_title": "Backend Developer",
        "jd_requirements": "Yeu cau Python, FastAPI.",
    }

    result = await validate_input(state)

    assert result["error"] == ""


# ---------------------------------------------------------------------------
# Graph compilation
# ---------------------------------------------------------------------------
def test_gap_analysis_graph_compiles_without_error():
    graph = create_gap_analysis_graph()
    assert graph is not None
    # A compiled LangGraph graph exposes the node names it was built from.
    assert "guardrail_check" in graph.nodes
    assert "validate_input" in graph.nodes

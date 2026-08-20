"""Gap Analysis Service — high-level facade over the CV Gap Analysis Agent.

This is the function the API layer (owned by agent_web, in `src/api/`)
should call from the `POST /api/v1/analysis/gap` endpoint. It hides the
LangGraph plumbing (state dicts, node names) behind a plain
input-in/dict-out function.

This service intentionally has NO database dependency — persisting the
result into the `cv_analyses` table (see system_architecture.md §3.3.4) is
agent_web's responsibility. Keeping this layer DB-free means it can be
unit-tested and reused (e.g. from a CLI/eval script) without a database.
"""

from __future__ import annotations

from typing import Any

from src.agents.gap_analysis.graph import create_gap_analysis_graph

# The compiled graph is stateless between invocations (all per-run data
# lives in the state dict passed to `.ainvoke()`), so one instance is built
# once at import time and reused for every call — building it fresh per
# request would just repeat the same node-registration work for no benefit.
_gap_analysis_graph = create_gap_analysis_graph()


async def analyze_cv_against_jd(
    *,
    cv_raw_text: str,
    cv_parsed_json: dict[str, Any] | None = None,
    jd_title: str,
    jd_requirements: str,
    jd_parsed_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the Gap Analysis Agent for one CV/JD pair.

    Returns a dict shaped like:
        {
            "match_score": 72.5,
            "matched_skills": [...],
            "partial_skills": [...],
            "missing_skills": [...],
            "gaps": {"skill_gaps": [...], "experience_gap": {...}, "education_requirement": "..."},
            "suggestions": [
                {"section", "original_text", "suggested_text", "reason", "status": "pending"},
                ...
            ],
        }

    Every entry in `suggestions` has already passed the anti-hallucination
    guardrail (src/agents/gap_analysis/nodes.py:guardrail_check) — it is
    safe to show directly to the student for Accept/Reject (HITL, per
    CLAUDE.md constraint 2). `status` starts as "pending"; use
    `apply_suggestion_decision` below to record the student's choice.

    Raises ValueError if the input is unusable (empty CV, or JD missing a
    title/requirements text).
    """
    result_state = await _gap_analysis_graph.ainvoke(
        {
            "cv_raw_text": cv_raw_text,
            "cv_parsed_json": cv_parsed_json or {},
            "jd_title": jd_title,
            "jd_requirements": jd_requirements,
            "jd_parsed_json": jd_parsed_json or {},
        }
    )
    if result_state.get("error"):
        raise ValueError(result_state["error"])
    return result_state["gap_analysis_result"]


def apply_suggestion_decision(
    gap_analysis_result: dict[str, Any],
    suggestion_index: int,
    *,
    accepted: bool,
    final_text: str | None = None,
) -> dict[str, Any]:
    """Record a student's Accept/Reject decision on one suggestion.

    Returns a NEW dict (does not mutate the input) with the target
    suggestion's `status` set to "accepted"/"rejected", and `final_text`
    set if the student edited the wording before accepting. This is a pure
    helper for callers that keep `gap_analysis_result` in memory (e.g. a
    session cache); persisting the decision to the `optimization_decisions`
    table is agent_web's job.

    Raises IndexError if `suggestion_index` is out of range.
    """
    suggestions = gap_analysis_result.get("suggestions", [])
    if not 0 <= suggestion_index < len(suggestions):
        raise IndexError(f"suggestion_index {suggestion_index} is out of range (0-{len(suggestions) - 1}).")

    updated_suggestions = [dict(item) for item in suggestions]
    target = updated_suggestions[suggestion_index]
    target["status"] = "accepted" if accepted else "rejected"
    if accepted and final_text is not None:
        target["final_text"] = final_text

    return {**gap_analysis_result, "suggestions": updated_suggestions}

"""LangGraph state schemas for the two AI agents in this project.

WHY TypedDict instead of a Pydantic model? LangGraph nodes are plain
functions that take the current state dict and return a *partial* dict of
the fields they updated (LangGraph merges it into the running state for
you). TypedDict gives us static typing for that dict shape without the
runtime validation overhead of Pydantic on every node call — validation of
LLM output already happens separately via `with_structured_output()`
(see src/services/cv_parser.py and the two agent packages).

`total=False` means every field is optional in the TypedDict sense — a
state dict is allowed to be missing keys it hasn't reached yet (e.g. before
`compute_match` has run, `match_score` simply isn't present). Nodes should
use `state.get("field", default)` rather than `state["field"]` for any
field that might not be populated yet at that point in the graph.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class GapAnalysisState(TypedDict, total=False):
    """State for the CV Gap Analysis Agent (see system_architecture.md §5.2).

    Flow: extract_cv_skills + extract_jd_requirements (parallel-ish) ->
    compute_match -> identify_gaps -> generate_suggestions ->
    guardrail_check -> gap_analysis_result.
    """

    # --- Input (set by the caller before invoking the graph) ---
    cv_raw_text: str  # Raw CV text (from cv_parser.extract_text)
    cv_parsed_json: dict[str, Any]  # Structured CV (from cv_parser.parse_cv)
    jd_title: str  # Job title, e.g. "Backend Developer"
    jd_requirements: str  # Raw JD text
    jd_parsed_json: dict[str, Any]  # Structured JD, if already parsed by the caller

    # --- Intermediate (filled in by nodes as the graph runs) ---
    cv_skills: dict[str, Any]  # Output of extract_cv_skills: {skills, experience_summary, education_summary, projects_summary}
    jd_requirements_extracted: dict[str, Any]  # Output of extract_jd_requirements: {required_skills, preferred_skills, min_years_experience, ...}
    matched_skills: list[str]  # Skills present in both CV and JD
    partial_skills: list[str]  # Skills the CV mentions but with weaker/unclear evidence than the JD wants
    missing_skills: list[str]  # JD skills with no evidence in the CV at all
    match_score: float  # 0-100, computed deterministically in compute_match (never invented by the LLM)
    gaps: dict[str, Any]  # Output of identify_gaps: structured gap breakdown used to prompt generate_suggestions

    # --- Suggestions pipeline (HITL — see class docstring in gap_analysis/nodes.py) ---
    draft_suggestions: list[dict[str, Any]]  # Raw LLM suggestions, BEFORE the anti-hallucination guardrail
    suggestions: list[dict[str, Any]]  # Suggestions AFTER guardrail_check — safe to show the student for Accept/Reject
    guardrail_notes: list[str]  # Human-readable reasons any draft suggestion was dropped (for logging/debugging)

    # --- Output ---
    gap_analysis_result: dict[str, Any]  # Final payload: match_score, matched/missing/partial skills, gaps, suggestions
    error: str  # Set (non-empty) by validate_input if the input is unusable; graph short-circuits to END


class InterviewAgentState(TypedDict, total=False):
    """State for the Mock Interview Agent (see system_architecture.md §5.3).

    One graph, three "operations" selected by the `operation` field:
      - "start":   generate the initial question set for a new session
      - "respond": evaluate one answer, decide STAR scores + optional follow-up
      - "report":  summarize a finished session into the final STAR report
    """

    operation: Literal["start", "respond", "report"]

    # --- Input shared across operations ---
    cv_text: str
    cv_parsed_json: dict[str, Any]
    jd_title: str
    jd_requirements: str
    num_questions: int  # Requested question count (5-7 per PRD F-05)

    # --- "start" operation ---
    interview_questions: list[str]  # Generated question set (output of generate_questions)

    # --- "respond" operation (one turn) ---
    question_text: str  # The question currently being answered
    user_answer: str  # Student's answer text
    is_follow_up: bool  # True if `question_text` was itself a follow-up question
    evaluation: dict[str, Any]  # Output of evaluate_response: STAR coverage classification + needs_follow_up
    follow_up_question: str  # Output of generate_followup, when needs_follow_up is True
    star_score: dict[str, float]  # Output of score_star for this turn: {situation, task, action, result} out of 25 each

    # --- Session history (accumulated by the caller across turns, not by the graph itself) ---
    qa_history: list[dict[str, Any]]  # [{question, answer, follow_up_question?, follow_up_answer?, star_score}, ...]

    # --- "report" operation ---
    final_report: dict[str, Any]  # {total_score, star_scores, strengths, improvements, recommendations}

    error: str

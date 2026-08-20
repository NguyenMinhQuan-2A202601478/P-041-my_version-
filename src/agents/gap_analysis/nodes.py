"""LangGraph nodes for the CV Gap Analysis Agent.

Graph order (see graph.py): validate_input -> extract_cv_skills ->
extract_jd_requirements -> compute_match -> identify_gaps ->
generate_suggestions -> guardrail_check -> END.

WHY is `compute_match` deterministic (plain Python) instead of asking the
LLM for a match score? Because a score the LLM makes up is not trustworthy
or reproducible — two runs on the same CV/JD could give different numbers.
This mirrors the project's rubric philosophy for STAR scoring in the
interview agent (see interview/nodes.py): let the LLM classify/extract,
but let deterministic code calculate anything numeric.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.agents.gap_analysis.prompts import (
    JD_EXTRACTION_SYSTEM_PROMPT,
    SUGGESTION_GENERATION_SYSTEM_PROMPT,
    build_suggestion_user_prompt,
)
from src.agents.state import GapAnalysisState
from src.services.llm import get_llm

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Structured output schemas for the two LLM calls in this graph
# --------------------------------------------------------------------------
class _JDRequirements(BaseModel):
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    min_years_experience: float = Field(default=0.0, ge=0)
    education_requirement: str = Field(default="")
    responsibilities: list[str] = Field(default_factory=list)


class _CVSuggestion(BaseModel):
    section: str = Field(description="CV section this bullet belongs to, e.g. 'experience'.")
    original_text: str = Field(description="Exact text quoted from the CV.")
    suggested_text: str = Field(description="Rewritten bullet.")
    reason: str = Field(default="")


class _SuggestionList(BaseModel):
    suggestions: list[_CVSuggestion] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Node 0: validate_input
# --------------------------------------------------------------------------
async def validate_input(state: GapAnalysisState) -> dict[str, Any]:
    """Reject obviously-unusable input before spending any LLM calls."""
    cv_text = (state.get("cv_raw_text") or "").strip()
    jd_title = (state.get("jd_title") or "").strip()
    jd_requirements = (state.get("jd_requirements") or "").strip()
    if not cv_text:
        return {"error": "CV has no content to analyze."}
    if not jd_title or not jd_requirements:
        return {"error": "The job description is missing a title or requirements text."}
    return {"error": ""}


# --------------------------------------------------------------------------
# Node 1: extract_cv_skills
# --------------------------------------------------------------------------
# WHY no LLM call here? The CV was already structured by
# src/services/cv_parser.py (which DID use an LLM, once, at upload time).
# Re-extracting the same information with another LLM call here would
# double the cost for no benefit (KPI: control LLM calls — see CLAUDE.md
# constraint 7). This node just consolidates what's already in
# `cv_parsed_json` into the shape the rest of the graph expects, with a
# lightweight text fallback for CVs that only have `cv_raw_text`.
def _dedupe_casefold(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


async def extract_cv_skills(state: GapAnalysisState) -> dict[str, Any]:
    parsed = state.get("cv_parsed_json") or {}
    skills = _dedupe_casefold([str(s) for s in parsed.get("skills", [])])

    experience_entries = parsed.get("experience", []) or []
    experience_summary = " ".join(
        str(entry.get("description", "")) for entry in experience_entries if isinstance(entry, dict)
    ).strip()

    education_entries = parsed.get("education", []) or []
    education_summary = "; ".join(
        f"{entry.get('degree', '')} - {entry.get('institution', '')}".strip(" -")
        for entry in education_entries
        if isinstance(entry, dict)
    ).strip()

    projects_entries = parsed.get("projects", []) or []
    projects_summary = "; ".join(str(entry.get("name", "")) for entry in projects_entries if isinstance(entry, dict))

    return {
        "cv_skills": {
            "skills": skills,
            "experience_summary": experience_summary,
            "education_summary": education_summary,
            "projects_summary": projects_summary,
        }
    }


# --------------------------------------------------------------------------
# Node 2: extract_jd_requirements
# --------------------------------------------------------------------------
async def extract_jd_requirements(state: GapAnalysisState) -> dict[str, Any]:
    """Structure the free-form JD text into required/preferred skills etc.

    Uses the LLM because JD text is prose (unlike the already-structured
    CV), so this is the one call in the graph where an LLM genuinely adds
    value over plain string matching.
    """
    already_parsed = state.get("jd_parsed_json") or {}
    if already_parsed.get("required_skills") or already_parsed.get("preferred_skills"):
        # Caller already supplied a structured JD (e.g. from a JD library
        # entry parsed once at creation time) — reuse it, no LLM call.
        return {"jd_requirements_extracted": already_parsed}

    llm = get_llm()
    structured_llm = llm.with_structured_output(_JDRequirements)
    messages = [
        SystemMessage(content=JD_EXTRACTION_SYSTEM_PROMPT),
        HumanMessage(content=f"Job title: {state['jd_title']}\n\nJob description:\n{state['jd_requirements']}"),
    ]
    try:
        result = await structured_llm.ainvoke(messages)
        parsed = result.model_dump() if isinstance(result, _JDRequirements) else dict(result)
    except Exception as exc:
        logger.warning("extract_jd_requirements: LLM call failed, using empty requirements: %s", exc)
        parsed = _JDRequirements().model_dump()
    return {"jd_requirements_extracted": parsed}


# --------------------------------------------------------------------------
# Node 3: compute_match (deterministic — no LLM)
# --------------------------------------------------------------------------
def _normalize_skill(skill: str) -> str:
    return re.sub(r"[^a-z0-9+#. ]", "", skill.casefold()).strip()


def _skill_present(skill: str, cv_skills_normalized: set[str], cv_text_casefold: str) -> bool:
    normalized = _normalize_skill(skill)
    if not normalized:
        return False
    if normalized in cv_skills_normalized:
        return True
    # Fall back to a whole-word search in the raw CV text, so a skill the
    # parser missed in `skills[]` (but that is genuinely written in the CV,
    # e.g. inside a project description) still counts as evidence.
    return re.search(rf"(?<!\w){re.escape(normalized)}(?!\w)", cv_text_casefold) is not None


async def compute_match(state: GapAnalysisState) -> dict[str, Any]:
    """Deterministically score CV-JD fit. Never delegated to the LLM —
    see module docstring for why."""
    cv_skills = state.get("cv_skills", {}).get("skills", [])
    cv_skills_normalized = {_normalize_skill(s) for s in cv_skills}
    cv_text_casefold = (state.get("cv_raw_text") or "").casefold()

    jd_req = state.get("jd_requirements_extracted", {})
    required = list(dict.fromkeys(jd_req.get("required_skills", [])))
    preferred = list(dict.fromkeys(jd_req.get("preferred_skills", [])))

    matched: list[str] = []
    missing: list[str] = []
    for skill in required + preferred:
        if _skill_present(skill, cv_skills_normalized, cv_text_casefold):
            matched.append(skill)
        else:
            missing.append(skill)

    # "Partial" = a required/preferred skill whose normalized name is a
    # substring of (or contains) something in the CV's skill list, e.g. JD
    # wants "PostgreSQL" and the CV lists "SQL" — related but not an exact
    # demonstrated match. This never overlaps with `matched` or `missing`.
    partial: list[str] = []
    still_missing: list[str] = []
    cv_skills_norm_list = list(cv_skills_normalized)
    for skill in missing:
        normalized = _normalize_skill(skill)
        is_partial = normalized and any(
            (normalized in cv_norm or cv_norm in normalized) and normalized != cv_norm
            for cv_norm in cv_skills_norm_list
            if cv_norm
        )
        (partial if is_partial else still_missing).append(skill)
    missing = still_missing

    # Weighted score: required skills count double a preferred skill; a
    # partial match counts as half credit. This is a simple, explainable
    # formula a student can audit — not a black box.
    required_weight, preferred_weight, partial_credit = 2.0, 1.0, 0.5
    max_points = len(required) * required_weight + len(preferred) * preferred_weight
    earned_points = 0.0
    for skill in required:
        weight = required_weight
        if skill in matched:
            earned_points += weight
        elif skill in partial:
            earned_points += weight * partial_credit
    for skill in preferred:
        weight = preferred_weight
        if skill in matched:
            earned_points += weight
        elif skill in partial:
            earned_points += weight * partial_credit

    match_score = round((earned_points / max_points) * 100, 1) if max_points > 0 else 0.0

    return {
        "matched_skills": matched,
        "partial_skills": partial,
        "missing_skills": missing,
        "match_score": match_score,
    }


# --------------------------------------------------------------------------
# Node 4: identify_gaps (deterministic — structures compute_match's output
# for the prompt in generate_suggestions, plus experience/education gaps)
# --------------------------------------------------------------------------
async def identify_gaps(state: GapAnalysisState) -> dict[str, Any]:
    jd_req = state.get("jd_requirements_extracted", {})
    required = set(jd_req.get("required_skills", []))
    missing = state.get("missing_skills", [])
    partial = state.get("partial_skills", [])

    skill_gaps = [
        {"skill": skill, "priority": "required" if skill in required else "preferred", "status": "missing"}
        for skill in missing
    ] + [
        {"skill": skill, "priority": "required" if skill in required else "preferred", "status": "partial"}
        for skill in partial
    ]

    min_years = float(jd_req.get("min_years_experience") or 0)
    experience_gap: dict[str, Any] = {}
    if min_years > 0:
        experience_gap = {
            "required_years": min_years,
            # We don't attempt to infer actual years of experience from free
            # text (too easy to get wrong / hallucinate) — the counselor or
            # student reviews this manually; we only surface the requirement.
            "note": f"JD requires at least {min_years} years of relevant experience — verify against the CV manually.",
        }

    return {
        "gaps": {
            "skill_gaps": skill_gaps,
            "experience_gap": experience_gap,
            "education_requirement": jd_req.get("education_requirement", ""),
        }
    }


# --------------------------------------------------------------------------
# Node 5: generate_suggestions (LLM — draft only, NOT yet safe to show)
# --------------------------------------------------------------------------
async def generate_suggestions(state: GapAnalysisState) -> dict[str, Any]:
    llm = get_llm()
    structured_llm = llm.with_structured_output(_SuggestionList)
    messages = [
        SystemMessage(content=SUGGESTION_GENERATION_SYSTEM_PROMPT),
        HumanMessage(
            content=build_suggestion_user_prompt(
                cv_raw_text=state["cv_raw_text"],
                jd_title=state["jd_title"],
                matched_skills=state.get("matched_skills", []),
                partial_skills=state.get("partial_skills", []),
                missing_skills=state.get("missing_skills", []),
            )
        ),
    ]
    try:
        result = await structured_llm.ainvoke(messages)
        suggestions = result.suggestions if isinstance(result, _SuggestionList) else []
        draft = [item.model_dump() if isinstance(item, _CVSuggestion) else dict(item) for item in suggestions]
    except Exception as exc:
        logger.warning("generate_suggestions: LLM call failed, no draft suggestions produced: %s", exc)
        draft = []
    return {"draft_suggestions": draft}


# --------------------------------------------------------------------------
# Node 6: guardrail_check (anti-hallucination gate — the last line of
# defense before a suggestion reaches the student's Accept/Reject screen)
# --------------------------------------------------------------------------
_NUMBER_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?%?\b")


def _verify_suggestion(item: dict[str, Any], cv_text_casefold: str, missing_skills: list[str]) -> str | None:
    """Return None if `item` passes every check, else a human-readable
    reason it was rejected."""
    original = str(item.get("original_text", "")).strip()
    suggested = str(item.get("suggested_text", "")).strip()
    if not original or not suggested:
        return "missing original_text or suggested_text"

    # Rule 1: original_text must actually be in the CV (near-verbatim quote).
    if original.casefold() not in cv_text_casefold:
        return "original_text is not a verbatim quote from the CV"

    # Rule 2: suggested_text must not introduce a skill the CV has no
    # evidence for at all.
    suggested_casefold = suggested.casefold()
    for skill in missing_skills:
        normalized = _normalize_skill(skill)
        if normalized and re.search(rf"(?<!\w){re.escape(normalized)}(?!\w)", suggested_casefold):
            return f"introduces missing skill '{skill}' with no evidence in the CV"

    # Rule 3: suggested_text must not add a number that wasn't in the
    # original quote (no fabricated metrics like "improved by 40%").
    original_numbers = set(_NUMBER_PATTERN.findall(original))
    suggested_numbers = set(_NUMBER_PATTERN.findall(suggested))
    if not suggested_numbers.issubset(original_numbers):
        return "adds a number/metric not present in the original text"

    return None


async def guardrail_check(state: GapAnalysisState) -> dict[str, Any]:
    """Verify every draft suggestion against the CV text before it is
    allowed to reach the student's Accept/Reject screen (HITL — see
    CLAUDE.md constraint 2). This is the final anti-hallucination gate;
    generate_suggestions already instructs the LLM not to fabricate, but we
    never trust an LLM output without independently re-checking it."""
    cv_text_casefold = (state.get("cv_raw_text") or "").casefold()
    missing_skills = state.get("missing_skills", [])

    verified: list[dict[str, Any]] = []
    notes: list[str] = []
    for item in state.get("draft_suggestions", []):
        rejection_reason = _verify_suggestion(item, cv_text_casefold, missing_skills)
        if rejection_reason:
            notes.append(f"Dropped suggestion ({item.get('original_text', '')[:60]!r}): {rejection_reason}")
            continue
        verified.append(
            {
                "section": item.get("section", ""),
                "original_text": item["original_text"],
                "suggested_text": item["suggested_text"],
                "reason": item.get("reason", ""),
                # HITL fields the API/frontend layer (owned by agent_web)
                # will populate as the student reviews each suggestion.
                "status": "pending",  # pending | accepted | rejected
            }
        )

    gap_analysis_result = {
        "match_score": state.get("match_score", 0.0),
        "matched_skills": state.get("matched_skills", []),
        "partial_skills": state.get("partial_skills", []),
        "missing_skills": state.get("missing_skills", []),
        "gaps": state.get("gaps", {}),
        "suggestions": verified,
    }

    return {
        "suggestions": verified,
        "guardrail_notes": notes,
        "gap_analysis_result": gap_analysis_result,
    }

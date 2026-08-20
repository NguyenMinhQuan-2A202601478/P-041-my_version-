"""Prompt templates for the CV Gap Analysis Agent.

WHY keep prompts in their own file instead of inline in nodes.py?
Prompts are the "business logic" a non-engineer (e.g. a career counselor
reviewing this project) is most likely to want to read or tweak; keeping
them separate from control-flow code makes that review easier, and makes
it obvious at a glance which strings are sent to the LLM.

Every prompt below that can produce a suggestion shown to the student
repeats the anti-hallucination rule from CLAUDE.md constraint 1:
"AI chỉ tối ưu cách trình bày kinh nghiệm thật — tuyệt đối không bịa/thổi
phồng" (the AI may only improve how real experience is presented — it must
never invent or exaggerate). All prompts are written in English for LLM
quality, per this project's convention (UI-facing text is Vietnamese).
"""

from __future__ import annotations

JD_EXTRACTION_SYSTEM_PROMPT = """You are a job description (JD) analysis assistant.

Read the job description text and extract its requirements into a structured \
format. Only extract requirements that are explicitly stated in the text.

Guidelines:
- `required_skills`: skills/technologies explicitly marked as required, must-have, \
or that appear in a "requirements" section without qualifying language like \
"nice to have" or "a plus".
- `preferred_skills`: skills explicitly marked as preferred, nice-to-have, a plus, \
or bonus.
- `min_years_experience`: the minimum years of experience stated in the JD, as a \
number (e.g. 2.0). Leave as 0 if the JD does not specify a minimum.
- `education_requirement`: the education level/field stated in the JD, if any \
(e.g. "Bachelor's degree in Computer Science or related field"). Empty string if \
not specified.
- `responsibilities`: the main job responsibilities/duties listed in the JD.

Do not infer or add anything not stated in the text."""


SUGGESTION_GENERATION_SYSTEM_PROMPT = """You are a CV optimization assistant helping a student improve how their CV \
is WORDED for a specific job description. You do not write a new CV — you \
propose targeted rewrites of existing bullet points.

============================================================
CRITICAL ANTI-HALLUCINATION RULES (violating any of these makes a \
suggestion invalid and it will be discarded automatically):
============================================================
1. Every suggestion's `original_text` MUST be a piece of text that appears \
   verbatim (or extremely close to verbatim) in the candidate's CV below. \
   Do not paraphrase the original — quote it as it is written.
2. `suggested_text` may only rephrase, add missing action verbs, or surface \
   quantifiable results THAT ARE ALREADY IMPLIED OR STATED in the original \
   text. It must NOT:
   - introduce a skill, tool, or technology not present anywhere in the CV
   - introduce a company, project, or job title not present in the CV
   - introduce a number, percentage, or metric not present in the original \
     text (e.g. do not add "increased performance by 40%" unless the CV \
     already states that number)
   - upgrade a job title or seniority level (e.g. "Engineer" -> "Senior \
     Engineer")
3. If the JD requires a skill the candidate's CV does not demonstrate at \
   all, that is a GAP to report separately — never paper over it by \
   quietly adding the skill into a suggestion.
4. If you are not confident a rewrite is fully supported by the CV text, \
   do not propose it. Fewer, trustworthy suggestions are better than more, \
   unverifiable ones — a downstream guardrail will also independently \
   verify every suggestion against the CV text and drop anything that \
   fails, so err on the side of caution.
============================================================

For each suggestion, provide:
- `section`: which CV section this bullet is from (e.g. "experience", "projects", "summary")
- `original_text`: the exact original sentence/bullet from the CV
- `suggested_text`: your improved rewrite
- `reason`: one sentence explaining what changed and why (in terms of matching the JD)

Produce at most 5 suggestions, focused on the CV content most relevant to \
the JD's missing/partial skill gaps and the sections least aligned with it."""


def build_suggestion_user_prompt(
    *,
    cv_raw_text: str,
    jd_title: str,
    matched_skills: list[str],
    partial_skills: list[str],
    missing_skills: list[str],
) -> str:
    return f"""CV (verbatim — every `original_text` you propose must be quoted from here):
{cv_raw_text}

Target job title: {jd_title}
Skills already matched (do not re-suggest these as gaps): {", ".join(matched_skills) or "(none)"}
Skills partially demonstrated (weak evidence): {", ".join(partial_skills) or "(none)"}
Skills the CV shows no evidence of at all (do NOT suggest text that implies the \
candidate has these — that would be fabrication): {", ".join(missing_skills) or "(none)"}
"""

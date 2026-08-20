"""CV Parser Service — turn an uploaded PDF/DOCX file into structured JSON.

Pipeline: file bytes -> raw text (local, no LLM) -> structured JSON (LLM).

WHY split "extract text" from "structure text" into two steps instead of
sending the raw file straight to the LLM?
  1. Extraction is deterministic and free (PyPDF/python-docx run locally);
     only the much smaller "structuring" step costs an LLM call.
  2. We keep `raw_text` around (see docs/architecture/system_architecture.md
     section 3 — `cvs.raw_text` column) for re-parsing later without asking
     the student to re-upload the file, and for the anti-hallucination
     checks in the Gap Analysis agent, which compare suggestions back
     against the original text.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Any

import docx
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from pypdf import PdfReader

from src.services.llm import get_llm

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {"pdf", "docx"}


# --------------------------------------------------------------------------
# Structured output schema
#
# WHY a Pydantic model instead of asking the LLM to "return JSON" and
# `json.loads`-ing the response text? `with_structured_output()` makes the
# provider itself constrain generation to this schema (function-calling /
# JSON-schema mode under the hood), so we don't have to defensively parse
# malformed JSON, fenced code blocks, etc.
# --------------------------------------------------------------------------
class EducationEntry(BaseModel):
    institution: str = Field(description="School/university name, exactly as written in the CV.")
    degree: str = Field(default="", description="Degree or program name, e.g. 'B.Sc. Computer Science'.")
    period: str = Field(default="", description="Time period as written, e.g. '2022 - 2026'.")
    details: str = Field(default="", description="Extra detail present in the text, e.g. GPA or honors.")


class ExperienceEntry(BaseModel):
    company: str = Field(description="Employer name, exactly as written in the CV.")
    role: str = Field(default="", description="Job title as written in the CV.")
    period: str = Field(default="", description="Time period as written, e.g. '06/2025 - 08/2025'.")
    description: str = Field(default="", description="Responsibilities/achievements as described in the CV.")


class ProjectEntry(BaseModel):
    name: str = Field(description="Project name/title as written in the CV.")
    description: str = Field(default="", description="Project description as written in the CV.")
    technologies: list[str] = Field(default_factory=list, description="Technologies explicitly mentioned for this project.")


class StructuredCV(BaseModel):
    """Structured CV data. Every field must come from the source text —
    see the anti-hallucination instructions in `_EXTRACTION_SYSTEM_PROMPT`.
    """

    full_name: str = Field(default="")
    email: str = Field(default="")
    phone: str = Field(default="")
    summary: str = Field(default="", description="Personal summary/objective statement, if the CV has one.")
    education: list[EducationEntry] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list, description="Technical and soft skills explicitly listed.")
    experience: list[ExperienceEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Text extraction (no LLM — pure parsing)
# --------------------------------------------------------------------------
def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF that has a text layer (not a scanned image)."""
    try:
        reader = PdfReader(BytesIO(file_bytes), strict=False)
    except Exception as exc:
        raise ValueError(f"Could not open PDF file: {exc}") from exc

    if reader.is_encrypted:
        # Try an empty password first — many "protected" PDFs are just
        # owner-password-locked (printing/copying restricted) but still
        # readable with no password.
        if reader.decrypt("") == 0:
            raise ValueError("PDF is password-protected and cannot be read.")

    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract text from a .docx file (paragraphs + table cells)."""
    try:
        document = docx.Document(BytesIO(file_bytes))
    except Exception as exc:
        raise ValueError(f"Could not open DOCX file: {exc}") from exc

    parts: list[str] = [para.text for para in document.paragraphs if para.text.strip()]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    parts.append(cell.text.strip())
    return "\n".join(parts).strip()


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Dispatch to the right extractor based on the file extension.

    Raises ValueError for empty files or unsupported formats — callers
    (the API layer) are expected to turn this into a 4xx response.
    """
    if not file_bytes:
        raise ValueError("The uploaded file is empty.")

    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file format '.{extension}'. Only PDF and DOCX are supported.")

    text = extract_text_from_pdf(file_bytes) if extension == "pdf" else extract_text_from_docx(file_bytes)
    if not text.strip():
        raise ValueError(
            "No extractable text found in this file. It may be a scanned/image-only document, "
            "which this parser does not OCR."
        )
    return text


# --------------------------------------------------------------------------
# LLM structuring step
# --------------------------------------------------------------------------
_EXTRACTION_SYSTEM_PROMPT = """You are a CV/resume parsing assistant.

Your ONLY job is to reorganize the CV text you are given into the requested \
structured schema. This is extraction, not generation.

CRITICAL RULES (violating these is a serious error):
- Use ONLY information that is literally present in the CV text below.
- Do NOT invent, infer, guess, or add any skill, employer, project, degree, \
date, or number that is not explicitly written in the text.
- Do NOT "improve" or embellish wording — copy phrases from the source text \
as closely as reasonable while fitting them into the schema fields.
- If a field's information is not present in the text, leave it empty \
(empty string or empty list) rather than making something up.
- If the CV is in Vietnamese, keep the extracted values in Vietnamese; \
do not translate them."""


def _build_extraction_messages(raw_text: str) -> list[HumanMessage | SystemMessage]:
    return [
        SystemMessage(content=_EXTRACTION_SYSTEM_PROMPT),
        HumanMessage(content=f"CV text:\n\n{raw_text}"),
    ]


async def structure_cv_with_llm(raw_text: str) -> dict[str, Any]:
    """Turn raw CV text into a structured dict matching `StructuredCV`.

    Uses `with_structured_output` so the model itself is constrained to the
    schema — see the module docstring for why.
    """
    llm = get_llm()
    structured_llm = llm.with_structured_output(StructuredCV)
    result = await structured_llm.ainvoke(_build_extraction_messages(raw_text))
    if isinstance(result, StructuredCV):
        return result.model_dump()
    if isinstance(result, dict):
        return result
    # Some providers/versions may return the schema instance under a
    # different wrapper; fail loudly rather than silently returning junk.
    raise ValueError(f"Unexpected structured output type from LLM: {type(result)!r}")


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------
async def parse_cv(file_bytes: bytes, filename: str) -> dict[str, Any]:
    """Parse an uploaded CV file into `{raw_text, parsed_json}`.

    This is the function the API layer (owned by agent_web) should call
    from the `/cvs/upload` endpoint. Raises ValueError with a
    student-readable message for empty files, unsupported formats, or
    files with no extractable text (see `extract_text`).
    """
    raw_text = extract_text(file_bytes, filename)
    try:
        parsed_json = await structure_cv_with_llm(raw_text)
    except Exception as exc:
        # An LLM outage/misconfiguration shouldn't block the student from
        # seeing their raw extracted text; the frontend can show raw_text
        # and let them retry structuring later. Only extraction failures
        # (above) are treated as hard errors.
        logger.warning("CV structuring via LLM failed, returning raw_text only: %s", exc)
        parsed_json = {}

    return {"raw_text": raw_text, "parsed_json": parsed_json}

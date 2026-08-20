"""Tests for src/services/cv_parser.py (F-02: Upload & Parse CV)."""

from __future__ import annotations

from io import BytesIO

import docx
import pytest

from src.services.cv_parser import (
    StructuredCV,
    extract_text,
    extract_text_from_docx,
    extract_text_from_pdf,
    parse_cv,
    structure_cv_with_llm,
)


# ---------------------------------------------------------------------------
# extract_text_from_pdf — mock PdfReader so this test doesn't need a real
# PDF file, per the QA task's "mock the file" guidance.
# ---------------------------------------------------------------------------
class _FakePage:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _FakeReader:
    def __init__(self, *_args, **_kwargs) -> None:
        self.is_encrypted = False
        self.pages = [_FakePage("Nguyen Van A"), _FakePage("Ky nang: Python, FastAPI")]

    def decrypt(self, _password: str) -> int:
        return 0


def test_extract_text_from_pdf_joins_page_text(monkeypatch):
    monkeypatch.setattr("src.services.cv_parser.PdfReader", _FakeReader)

    text = extract_text_from_pdf(b"%PDF-1.4 fake bytes for testing")

    assert text == "Nguyen Van A\nKy nang: Python, FastAPI"


def test_extract_text_from_pdf_encrypted_and_undecryptable_raises(monkeypatch):
    class _EncryptedReader(_FakeReader):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.is_encrypted = True

        def decrypt(self, _password: str) -> int:
            return 0  # 0 == failed to decrypt, per pypdf's convention

    monkeypatch.setattr("src.services.cv_parser.PdfReader", _EncryptedReader)

    with pytest.raises(ValueError, match="password-protected"):
        extract_text_from_pdf(b"%PDF-1.4 fake bytes")


def test_extract_text_from_pdf_with_garbage_bytes_raises_value_error():
    with pytest.raises(ValueError):
        extract_text_from_pdf(b"this is not a pdf file at all")


def test_extract_text_from_pdf_with_no_text_layer_returns_empty_string(monkeypatch):
    class _BlankReader(_FakeReader):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.pages = [_FakePage(""), _FakePage("")]

    monkeypatch.setattr("src.services.cv_parser.PdfReader", _BlankReader)

    assert extract_text_from_pdf(b"%PDF-1.4 fake bytes") == ""


# ---------------------------------------------------------------------------
# extract_text_from_docx — a real (small) .docx built in-memory, since
# python-docx makes this cheap and avoids over-mocking a working library.
# ---------------------------------------------------------------------------
def _build_docx_bytes(paragraphs: list[str]) -> bytes:
    document = docx.Document()
    for text in paragraphs:
        document.add_paragraph(text)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_extract_text_from_docx_reads_paragraphs():
    file_bytes = _build_docx_bytes(["Nguyen Van A", "Ky nang: Python, FastAPI, PostgreSQL"])

    text = extract_text_from_docx(file_bytes)

    assert "Nguyen Van A" in text
    assert "Ky nang: Python, FastAPI, PostgreSQL" in text


def test_extract_text_from_docx_with_invalid_bytes_raises_value_error():
    with pytest.raises(ValueError):
        extract_text_from_docx(b"not a docx file")


# ---------------------------------------------------------------------------
# extract_text — dispatch + validation
# ---------------------------------------------------------------------------
def test_extract_text_rejects_empty_file():
    with pytest.raises(ValueError, match="empty"):
        extract_text(b"", "resume.pdf")


def test_extract_text_rejects_unsupported_extension():
    with pytest.raises(ValueError, match="Unsupported"):
        extract_text(b"some content", "resume.txt")


def test_extract_text_rejects_file_with_no_extractable_text(monkeypatch):
    class _BlankReader(_FakeReader):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.pages = [_FakePage("")]

    monkeypatch.setattr("src.services.cv_parser.PdfReader", _BlankReader)

    with pytest.raises(ValueError, match="No extractable text"):
        extract_text(b"%PDF-1.4 fake bytes", "resume.pdf")


def test_extract_text_dispatches_docx_by_extension():
    file_bytes = _build_docx_bytes(["Nguyen Van A"])
    assert "Nguyen Van A" in extract_text(file_bytes, "resume.docx")


# ---------------------------------------------------------------------------
# structure_cv_with_llm / parse_cv — mock the LLM, per the QA task's
# constraint not to require real API keys.
# ---------------------------------------------------------------------------
class _FakeStructuredLLM:
    def __init__(self, result) -> None:
        self._result = result

    async def ainvoke(self, _messages):
        return self._result


class _FakeLLM:
    def __init__(self, structured_result) -> None:
        self._structured_result = structured_result

    def with_structured_output(self, _schema):
        return _FakeStructuredLLM(self._structured_result)


async def test_structure_cv_with_llm_returns_dict_from_structured_output(monkeypatch):
    fake_result = StructuredCV(full_name="Nguyen Van A", skills=["Python", "FastAPI"])
    monkeypatch.setattr("src.services.cv_parser.get_llm", lambda: _FakeLLM(fake_result))

    parsed = await structure_cv_with_llm("Nguyen Van A - Python, FastAPI")

    assert parsed["full_name"] == "Nguyen Van A"
    assert parsed["skills"] == ["Python", "FastAPI"]


async def test_parse_cv_happy_path_returns_raw_text_and_parsed_json(monkeypatch):
    file_bytes = _build_docx_bytes(["Nguyen Van A", "Ky nang: Python, FastAPI"])
    fake_result = StructuredCV(full_name="Nguyen Van A", skills=["Python", "FastAPI"])
    monkeypatch.setattr("src.services.cv_parser.get_llm", lambda: _FakeLLM(fake_result))

    result = await parse_cv(file_bytes, "resume.docx")

    assert "Nguyen Van A" in result["raw_text"]
    assert result["parsed_json"]["full_name"] == "Nguyen Van A"


async def test_parse_cv_falls_back_to_empty_parsed_json_when_llm_fails(monkeypatch):
    file_bytes = _build_docx_bytes(["Nguyen Van A"])

    async def _boom(_raw_text):
        raise RuntimeError("LLM outage")

    monkeypatch.setattr("src.services.cv_parser.structure_cv_with_llm", _boom)

    result = await parse_cv(file_bytes, "resume.docx")

    assert "Nguyen Van A" in result["raw_text"]
    assert result["parsed_json"] == {}


async def test_parse_cv_with_empty_file_raises_value_error():
    with pytest.raises(ValueError):
        await parse_cv(b"", "resume.docx")

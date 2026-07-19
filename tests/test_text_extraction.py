"""Unit tests for `forte.services.text_extraction.extract_text`."""

from __future__ import annotations

from pathlib import Path

import pytest

from forte.services.text_extraction import UnsupportedFileTypeError, extract_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_text_md(tmp_path: Path) -> None:
    p = tmp_path / "note.md"
    p.write_text("# Title\n\nSome body text.", encoding="utf-8")
    assert extract_text(p) == "# Title\n\nSome body text."


def test_extract_text_txt(tmp_path: Path) -> None:
    p = tmp_path / "note.txt"
    p.write_text("plain text content", encoding="utf-8")
    assert extract_text(p) == "plain text content"


def test_extract_text_docx() -> None:
    text = extract_text(FIXTURES / "sample.docx")
    assert text.strip() != ""
    assert "Hello from docx fixture." in text
    assert "Second paragraph." in text


def test_extract_text_pdf() -> None:
    text = extract_text(FIXTURES / "sample.pdf")
    assert text.strip() != ""
    assert "Hello from PDF fixture." in text


def test_extract_text_unsupported_extension(tmp_path: Path) -> None:
    p = tmp_path / "image.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(UnsupportedFileTypeError):
        extract_text(p)

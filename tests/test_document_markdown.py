"""Unit tests for document markdown (frontmatter) serialization — pure, no I/O."""

from __future__ import annotations

import pytest

from forte.domain.document import Document, compute_content_hash
from forte.domain.document_markdown import (
    ParsedDocument,
    from_markdown,
    to_markdown,
)


def test_round_trip_recovers_source_path_hash_ingested_at_and_body() -> None:
    document = Document(
        name="meeting notes",
        source_path="/Users/ben/notes/meeting.md",
        content_hash="abc123",
        ingested_at="2026-07-19T12:00:00+00:00",
        status="processed",
    )

    parsed = from_markdown(to_markdown(document, "Meeting notes.\n\nSecond paragraph."))

    assert parsed == ParsedDocument(
        name="meeting notes",
        source_path="/Users/ben/notes/meeting.md",
        content_hash="abc123",
        ingested_at="2026-07-19T12:00:00+00:00",
        body="Meeting notes.\n\nSecond paragraph.",
    )


def test_empty_body_round_trips() -> None:
    document = Document(
        name="a",
        source_path="a.txt",
        content_hash="deadbeef",
        ingested_at="2026-07-19T12:00:00+00:00",
        status="processed",
    )

    parsed = from_markdown(to_markdown(document, ""))

    assert parsed.body == ""


def test_values_with_special_characters_round_trip() -> None:
    document = Document(
        name="weird file",
        source_path="/tmp/weird: path/file.md",
        content_hash="hash",
        ingested_at="2026-07-19T12:00:00+00:00",
        status="processed",
    )

    parsed = from_markdown(to_markdown(document, 'a: b, c # d\nhe said "hi"'))

    assert parsed.source_path == "/tmp/weird: path/file.md"
    assert parsed.body == 'a: b, c # d\nhe said "hi"'


def test_from_markdown_requires_frontmatter() -> None:
    with pytest.raises(ValueError):
        from_markdown("just a body, no frontmatter\n")


def test_compute_content_hash_is_stable_for_identical_bytes() -> None:
    data = b"identical content"
    assert compute_content_hash(data) == compute_content_hash(data)


def test_compute_content_hash_differs_for_different_bytes() -> None:
    assert compute_content_hash(b"one") != compute_content_hash(b"two")

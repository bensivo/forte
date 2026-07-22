"""Unit tests for `forte.services.chunking.chunk_text`."""

from __future__ import annotations

import pytest

from forte.services.chunking import chunk_text, chunk_text_with_index


def test_chunk_text_multi_heading_document_splits_into_sections() -> None:
    text = (
        "# Section One\n"
        "Intro paragraph for section one.\n\n"
        "# Section Two\n"
        "Intro paragraph for section two.\n\n"
        "# Section Three\n"
        "Intro paragraph for section three."
    )
    chunks = chunk_text(text, max_chars=1000)

    # All three headings fit comfortably under max_chars, so they pack into
    # a single chunk, but each section must still be present in full and
    # in order.
    assert len(chunks) == 1
    joined = chunks[0]
    assert "# Section One" in joined
    assert "# Section Two" in joined
    assert "# Section Three" in joined
    assert joined.index("# Section One") < joined.index("# Section Two")
    assert joined.index("# Section Two") < joined.index("# Section Three")


def test_chunk_text_multi_heading_document_splits_when_over_max_chars() -> None:
    text = (
        "# Section One\n"
        + ("a" * 40 + "\n\n")
        + "# Section Two\n"
        + ("b" * 40 + "\n\n")
        + "# Section Three\n"
        + ("c" * 40)
    )
    chunks = chunk_text(text, max_chars=60)

    assert len(chunks) == 3
    assert "# Section One" in chunks[0]
    assert "a" * 40 in chunks[0]
    assert "# Section Two" in chunks[1]
    assert "b" * 40 in chunks[1]
    assert "# Section Three" in chunks[2]
    assert "c" * 40 in chunks[2]
    for chunk in chunks:
        assert len(chunk) <= 60


def test_chunk_text_hard_splits_single_oversized_paragraph() -> None:
    long_paragraph = "word " * 400  # well over 1000 chars, no blank lines
    chunks = chunk_text(long_paragraph, max_chars=100)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 100
    # Reassembling the pieces reproduces the (stripped) original text.
    assert "".join(chunks) == long_paragraph.strip()


def test_chunk_text_short_body_returns_one_chunk() -> None:
    text = "Just a short note with a single paragraph."
    chunks = chunk_text(text, max_chars=1000)
    assert chunks == [text]


def test_chunk_text_empty_input_returns_empty_list() -> None:
    assert chunk_text("", max_chars=1000) == []


def test_chunk_text_whitespace_only_input_returns_empty_list() -> None:
    assert chunk_text("   \n\n\t  \n  ", max_chars=1000) == []


def test_chunk_text_is_deterministic() -> None:
    text = (
        "# Title\n"
        "Some intro text that spans a bit.\n\n"
        "## Subsection\n"
        "More content here, describing things in detail.\n\n"
        "Final trailing paragraph without a heading."
    )
    first = chunk_text(text, max_chars=80)
    second = chunk_text(text, max_chars=80)
    assert first == second


def test_chunk_text_invalid_max_chars_raises() -> None:
    with pytest.raises(ValueError):
        chunk_text("some text", max_chars=0)


def test_chunk_text_with_index_pairs_chunks_with_position() -> None:
    text = "# A\nfirst\n\n# B\nsecond"
    indexed = chunk_text_with_index(text, max_chars=1000)
    plain = chunk_text(text, max_chars=1000)

    assert indexed == list(enumerate(plain))

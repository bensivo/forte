import re
from pathlib import Path

from forte.client.fs_document_searcher import FsDocumentSearcher
from forte.model.vault import VaultContext


def _write_processed(root: Path, doc_id: str, body: str, name: str = "doc") -> None:
    processed_dir = root / "docs" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    frontmatter = (
        "---\n"
        f"name: {name}\n"
        "source_path: /tmp/src.txt\n"
        "content_hash: abc123\n"
        "ingested_at: '2026-08-11T00:00:00+00:00'\n"
        "---\n\n"
    )
    (processed_dir / f"{doc_id}.md").write_text(frontmatter + body, encoding="utf-8")


def _context(root: Path) -> VaultContext:
    context = VaultContext()
    context.set_root(root)
    return context


def test_finds_match_with_correct_body_relative_line_number(tmp_path):
    # Given: a document whose body has a match on its second line
    _write_processed(tmp_path, "1", "first line\nsecond line has apple\nthird line")
    searcher = FsDocumentSearcher(_context(tmp_path))

    # When: searching for "apple"
    results = searcher.search(re.compile("apple"), None)

    # Then: one match is returned, on 1-based body-relative line 2
    assert len(results) == 1
    doc_id, matches = results[0]
    assert doc_id == 1
    assert len(matches) == 1
    assert matches[0].line_number == 2
    assert matches[0].line == "second line has apple"


def test_frontmatter_text_does_not_match(tmp_path):
    # Given: a document whose frontmatter contains a word not present in the body
    _write_processed(tmp_path, "1", "just a body\nwith no matches", name="apple-name")
    searcher = FsDocumentSearcher(_context(tmp_path))

    # When: searching for text that only appears in the frontmatter
    results = searcher.search(re.compile("apple-name"), None)

    # Then: no matches are found
    assert results == []


def test_multiple_matches_in_one_file(tmp_path):
    # Given: a document with matches on two separate lines
    _write_processed(tmp_path, "1", "apple one\nno match here\napple two")
    searcher = FsDocumentSearcher(_context(tmp_path))

    # When: searching for "apple"
    results = searcher.search(re.compile("apple"), None)

    # Then: both matching lines are returned in order
    doc_id, matches = results[0]
    assert [m.line_number for m in matches] == [1, 3]


def test_limit_per_document_caps_matches(tmp_path):
    # Given: a document with three matching lines
    _write_processed(tmp_path, "1", "apple\napple\napple")
    searcher = FsDocumentSearcher(_context(tmp_path))

    # When: searching with limit_per_document=2
    results = searcher.search(re.compile("apple"), 2)

    # Then: only the first two matches are collected
    doc_id, matches = results[0]
    assert len(matches) == 2


def test_non_integer_filename_stem_is_skipped(tmp_path):
    # Given: a processed file whose stem is not an integer, alongside a valid one
    _write_processed(tmp_path, "not-an-id", "apple")
    _write_processed(tmp_path, "2", "apple")
    searcher = FsDocumentSearcher(_context(tmp_path))

    # When: searching for "apple"
    results = searcher.search(re.compile("apple"), None)

    # Then: only the valid integer-stem document is returned
    assert len(results) == 1
    assert results[0][0] == 2


def test_malformed_file_without_frontmatter_is_skipped(tmp_path):
    # Given: a processed directory with one malformed file (no frontmatter) and one valid file
    processed_dir = tmp_path / "docs" / "processed"
    processed_dir.mkdir(parents=True)
    (processed_dir / "1.md").write_text("just plain text, no frontmatter at all", encoding="utf-8")
    _write_processed(tmp_path, "2", "apple")
    searcher = FsDocumentSearcher(_context(tmp_path))

    # When: searching for "apple"
    results = searcher.search(re.compile("apple"), None)

    # Then: the malformed file is skipped, and the valid file still matches
    assert len(results) == 1
    assert results[0][0] == 2


def test_missing_processed_dir_returns_empty_list(tmp_path):
    # Given: a vault root with no docs/processed directory at all
    searcher = FsDocumentSearcher(_context(tmp_path))

    # When: searching
    results = searcher.search(re.compile("apple"), None)

    # Then: an empty list is returned, not an error
    assert results == []


def test_spans_correct_for_line_with_two_hits(tmp_path):
    # Given: a document with a line containing two occurrences of the pattern
    _write_processed(tmp_path, "1", "apple and apple again")
    searcher = FsDocumentSearcher(_context(tmp_path))

    # When: searching for "apple"
    results = searcher.search(re.compile("apple"), None)

    # Then: both spans are captured on the single matching line
    doc_id, matches = results[0]
    assert len(matches) == 1
    assert matches[0].spans == [(0, 5), (10, 15)]

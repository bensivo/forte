import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from forte.interface.document_db import IDocumentDb
from forte.interface.document_searcher import IDocumentSearcher
from forte.model.document import Document, DocumentMatch, InvalidSearchQueryError
from forte.service.document_service import DocumentService


class FakeDocumentSearcher(IDocumentSearcher):
    """Fake IDocumentSearcher that returns canned results and records the
    pattern/limit it was called with, so tests can assert on the compiled
    pattern's text and flags without depending on a real scan."""

    def __init__(self, results: list[tuple[int, list[DocumentMatch]]]):
        self._results = results
        self.called = False
        self.last_pattern: re.Pattern | None = None
        self.last_limit_per_document: int | None = None

    def search(
        self, pattern: re.Pattern, limit_per_document: int | None
    ) -> list[tuple[int, list[DocumentMatch]]]:
        self.called = True
        self.last_pattern = pattern
        self.last_limit_per_document = limit_per_document
        return self._results


class FakeDocumentDb(IDocumentDb):
    """Fake IDocumentDb backed by an in-memory dict of documents."""

    def __init__(self, documents: list[Document]):
        self._documents = {doc.id: doc for doc in documents}

    def find_by_identity(self, source_path: str, content_hash: str) -> Document | None:
        raise NotImplementedError

    def add(self, source_path: Path, content_hash: str, extracted_text: str, name: str):
        raise NotImplementedError

    def add_text(self, name: str, content_hash: str, text: str):
        raise NotImplementedError

    def list(self) -> list[Document]:
        return sorted(self._documents.values(), key=lambda d: d.id or 0)

    def get(self, id: int) -> Document | None:
        return self._documents.get(id)

    def read_processed(self, id: int) -> str | None:
        raise NotImplementedError

    def remove(self, id: int) -> None:
        raise NotImplementedError


def _document(id: int, name: str = "doc") -> Document:
    return Document(
        name=name,
        source_path=f"/tmp/{name}.txt",
        content_hash="hash",
        ingested_at=datetime.now(timezone.utc).isoformat(),
        status="processed",
        raw_path=f"raw/{id}.txt",
        processed_path=f"processed/{id}.md",
        id=id,
    )


def _match(line_number: int, line: str = "some line") -> DocumentMatch:
    return DocumentMatch(line_number=line_number, line=line, spans=[(0, 4)])


def _make_service(searcher: FakeDocumentSearcher, documents: list[Document]) -> DocumentService:
    return DocumentService(
        document_db=FakeDocumentDb(documents),
        mention_db=None,  # type: ignore[arg-type]
        entity_db=None,  # type: ignore[arg-type]
        editor=None,  # type: ignore[arg-type]
        document_searcher=searcher,
        entity_picker=None,  # type: ignore[arg-type]
        search_entities=None,  # type: ignore[arg-type]
    )


def test_literal_match_returns_document_and_matches():
    # Given: a searcher that reports a hit in document 1
    doc = _document(1)
    searcher = FakeDocumentSearcher([(1, [_match(1, "an apple a day")])])
    service = _make_service(searcher, [doc])

    # When: searching for a literal query
    results = service.search_documents("apple")

    # Then: the document and its match are returned
    assert len(results) == 1
    assert results[0].document == doc
    assert len(results[0].matches) == 1
    assert results[0].matches[0].line_number == 1


def test_default_search_is_case_insensitive():
    # Given: a fake searcher recording the compiled pattern
    searcher = FakeDocumentSearcher([])
    service = _make_service(searcher, [])

    # When: searching without case_sensitive
    service.search_documents("Apple")

    # Then: the compiled pattern has the IGNORECASE flag set
    assert searcher.called
    assert searcher.last_pattern.flags & re.IGNORECASE


def test_case_sensitive_disables_ignorecase_flag():
    # Given: a fake searcher recording the compiled pattern
    searcher = FakeDocumentSearcher([])
    service = _make_service(searcher, [])

    # When: searching with case_sensitive=True
    service.search_documents("Apple", case_sensitive=True)

    # Then: the compiled pattern does not have IGNORECASE set
    assert searcher.called
    assert not (searcher.last_pattern.flags & re.IGNORECASE)


def test_regex_mode_compiles_query_as_pattern():
    # Given: a fake searcher recording the compiled pattern
    searcher = FakeDocumentSearcher([])
    service = _make_service(searcher, [])

    # When: searching with regex=True
    service.search_documents(r"ap+le", regex=True)

    # Then: the pattern text is used as-is (not escaped)
    assert searcher.last_pattern.pattern == r"ap+le"


def test_regex_compile_failure_raises_invalid_search_query_error():
    # Given: a malformed regex query
    searcher = FakeDocumentSearcher([])
    service = _make_service(searcher, [])

    # When/Then: searching with regex=True raises InvalidSearchQueryError,
    # including the underlying re.error message, and never calls the searcher
    with pytest.raises(InvalidSearchQueryError) as exc_info:
        service.search_documents("(unclosed", regex=True)
    assert not searcher.called
    # The underlying re.error message should be included somewhere in the text.
    assert "unterminated subpattern" in str(exc_info.value)


def test_empty_query_raises_before_searcher_is_called():
    # Given: an empty query
    searcher = FakeDocumentSearcher([])
    service = _make_service(searcher, [])

    # When/Then: searching raises InvalidSearchQueryError and never calls the searcher
    with pytest.raises(InvalidSearchQueryError):
        service.search_documents("")
    assert not searcher.called


def test_whitespace_only_query_raises_before_searcher_is_called():
    # Given: a whitespace-only query
    searcher = FakeDocumentSearcher([])
    service = _make_service(searcher, [])

    # When/Then: searching raises InvalidSearchQueryError and never calls the searcher
    with pytest.raises(InvalidSearchQueryError):
        service.search_documents("   ")
    assert not searcher.called


def test_limit_per_document_is_passed_through():
    # Given: a fake searcher recording the limit it was called with
    searcher = FakeDocumentSearcher([])
    service = _make_service(searcher, [])

    # When: searching with a limit_per_document
    service.search_documents("apple", limit_per_document=3)

    # Then: the same limit was passed to the searcher
    assert searcher.last_limit_per_document == 3


def test_results_ordered_by_document_id_and_matches_by_line_number():
    # Given: a searcher returning documents out of id order, and matches out
    # of line-number order within one document
    doc1 = _document(1)
    doc2 = _document(2)
    searcher = FakeDocumentSearcher(
        [
            (2, [_match(1)]),
            (1, [_match(3), _match(1), _match(2)]),
        ]
    )
    service = _make_service(searcher, [doc1, doc2])

    # When: searching
    results = service.search_documents("apple")

    # Then: results are ordered by document id
    assert [r.document.id for r in results] == [1, 2]
    # Then: matches within document 1 are ordered by line number
    assert [m.line_number for m in results[0].matches] == [1, 2, 3]


def test_orphaned_processed_file_is_dropped():
    # Given: a searcher reporting a hit for a document id with no db row
    doc1 = _document(1)
    searcher = FakeDocumentSearcher(
        [
            (1, [_match(1)]),
            (99, [_match(1)]),
        ]
    )
    service = _make_service(searcher, [doc1])

    # When: searching
    results = service.search_documents("apple")

    # Then: only the document with a matching db row is returned
    assert len(results) == 1
    assert results[0].document.id == 1


def test_literal_query_with_regex_metacharacters_is_escaped():
    # Given: a fake searcher recording the compiled pattern
    searcher = FakeDocumentSearcher([])
    service = _make_service(searcher, [])

    # When: searching for a literal query containing regex metacharacters
    service.search_documents("v1.2 (draft)")

    # Then: the pattern matches the literal text, not the regex semantics
    assert searcher.last_pattern.search("v1.2 (draft)") is not None
    assert searcher.last_pattern.search("v1x2 xdraftx") is None

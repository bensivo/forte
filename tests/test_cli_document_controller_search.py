"""Unit tests for CliDocumentController's `doc search` subcommand.

Per the style guide, controllers are tested with a real user interface
(`click.testing.CliRunner`) driving the actual `click.Group`, but a fake
`DocumentService` standing in for the real one - so these tests only verify
what the controller renders and how it calls the service, not document
search behavior itself (that's covered by `test_document_service_search.py`
and `test_fs_document_searcher.py`).
"""

from __future__ import annotations

from pathlib import Path

import click
from click.testing import CliRunner

from forte.controller.cli_document_controller import CliDocumentController
from forte.model.document import (
    Document,
    DocumentMatch,
    DocumentSearchResult,
    InvalidSearchQueryError,
)
from forte.model.vault import Vault, VaultContext


class _FakeVaultService:
    """Stands in for VaultService: always resolves to a single fake vault."""

    def resolve_vault(self, vault_name: str | None) -> Vault:
        return Vault(name=vault_name or "default", path=Path("/fake/vault"))


class _FakeDocumentService:
    """Stands in for DocumentService, recording `search_documents` calls and
    returning a scripted result (or raising a scripted error)."""

    def __init__(self, results=None, error: Exception | None = None):
        self.results = results if results is not None else []
        self.error = error
        self.calls: list[dict] = []

    def search_documents(
        self,
        query: str,
        *,
        case_sensitive: bool = False,
        regex: bool = False,
        limit_per_document: int | None = None,
    ):
        self.calls.append(
            {
                "query": query,
                "case_sensitive": case_sensitive,
                "regex": regex,
                "limit_per_document": limit_per_document,
            }
        )
        if self.error is not None:
            raise self.error
        return self.results


def _document(id: int, name: str) -> Document:
    return Document(
        id=id,
        name=name,
        source_path=f"/src/{name}.md",
        content_hash="abc123",
        ingested_at="2026-08-11T00:00:00",
        status="processed",
    )


def _cli(document_service) -> click.Group:
    """Build a standalone `main` group with just the `doc` command wired to
    the given fake service."""
    vault_service = _FakeVaultService()
    vault_context = VaultContext()
    controller = CliDocumentController(document_service, vault_service, vault_context)

    @click.group()
    def main() -> None:
        pass

    main.add_command(controller.group())
    return main


def test_search_multiple_documents_grouped_output():
    doc1 = _document(3, "Acme Kickoff Notes")
    doc2 = _document(7, "Weekly Sync")
    results = [
        DocumentSearchResult(
            document=doc1,
            matches=[
                DocumentMatch(
                    line_number=12,
                    line="we agreed the launch date is March 4th",
                    spans=[(14, 25)],
                ),
                DocumentMatch(
                    line_number=47,
                    line="launch date moved, pending Acme signoff",
                    spans=[(0, 11)],
                ),
            ],
        ),
        DocumentSearchResult(
            document=doc2,
            matches=[
                DocumentMatch(
                    line_number=3,
                    line="launch date is still the open question",
                    spans=[(0, 11)],
                ),
            ],
        ),
    ]
    service = _FakeDocumentService(results=results)
    main = _cli(service)
    runner = CliRunner()

    result = runner.invoke(main, ["doc", "search", "launch date"])

    assert result.exit_code == 0, result.output
    output = result.output
    assert "doc #3: Acme Kickoff Notes" in output
    assert "doc #7: Weekly Sync" in output
    assert "line 12:" in output and "we agreed the launch date is March 4th" in output
    assert "line 47:" in output and "launch date moved, pending Acme signoff" in output
    assert "line 3:" in output and "launch date is still the open question" in output
    assert "2 documents, 3 matches" in output
    # doc #3's group should come before doc #7's group.
    assert output.index("#3") < output.index("#7")


def test_search_single_document():
    doc = _document(1, "Notes")
    results = [
        DocumentSearchResult(
            document=doc,
            matches=[DocumentMatch(line_number=5, line="hello world", spans=[(0, 5)])],
        ),
    ]
    service = _FakeDocumentService(results=results)
    main = _cli(service)
    runner = CliRunner()

    result = runner.invoke(main, ["doc", "search", "hello"])

    assert result.exit_code == 0, result.output
    assert "doc #1: Notes" in result.output
    assert "line 5:" in result.output and "hello world" in result.output
    assert "1 document, 1 match" in result.output


def test_search_no_matches_prints_message_and_exits_zero():
    service = _FakeDocumentService(results=[])
    main = _cli(service)
    runner = CliRunner()

    result = runner.invoke(main, ["doc", "search", "nonexistent"])

    assert result.exit_code == 0, result.output
    assert "No matches." in result.output


def test_search_invalid_query_becomes_clean_click_exception():
    service = _FakeDocumentService(error=InvalidSearchQueryError("Search query must not be empty."))
    main = _cli(service)
    runner = CliRunner()

    result = runner.invoke(main, ["doc", "search", ""])

    assert result.exit_code != 0
    assert "Search query must not be empty." in result.output
    # No traceback should reach the user.
    assert "Traceback" not in result.output


def test_search_forwards_options_to_service():
    service = _FakeDocumentService(results=[])
    main = _cli(service)
    runner = CliRunner()

    result = runner.invoke(
        main,
        ["doc", "search", "foo.*bar", "--case-sensitive", "--regex", "--limit", "5"],
    )

    assert result.exit_code == 0, result.output
    assert len(service.calls) == 1
    call = service.calls[0]
    assert call["query"] == "foo.*bar"
    assert call["case_sensitive"] is True
    assert call["regex"] is True
    assert call["limit_per_document"] == 5


def test_search_default_options_are_literal_and_case_insensitive():
    service = _FakeDocumentService(results=[])
    main = _cli(service)
    runner = CliRunner()

    result = runner.invoke(main, ["doc", "search", "plain text"])

    assert result.exit_code == 0, result.output
    call = service.calls[0]
    assert call["case_sensitive"] is False
    assert call["regex"] is False
    assert call["limit_per_document"] is None


def test_search_help_documents_literal_default_and_regex_option():
    service = _FakeDocumentService(results=[])
    main = _cli(service)
    runner = CliRunner()

    result = runner.invoke(main, ["doc", "search", "--help"])

    assert result.exit_code == 0, result.output
    assert "--regex" in result.output
    assert "literal" in result.output.lower() or "literally" in result.output.lower()


def test_doc_help_lists_search():
    service = _FakeDocumentService(results=[])
    main = _cli(service)
    runner = CliRunner()

    result = runner.invoke(main, ["doc", "--help"])

    assert result.exit_code == 0, result.output
    assert "search" in result.output

"""Unit tests for CliDocumentController's `doc link-interactive` subcommand.

Per the style guide, controllers are tested with a real user interface
(`click.testing.CliRunner`) driving the actual `click.Group`, but a fake
`DocumentService` standing in for the real one - so these tests only verify
what the controller renders, how it calls the service, and how it handles
the TTY / no-entities / abort guards, not the picker or linking behavior
itself (that's covered by `test_document_service_link_interactive.py`).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

import forte.controller.cli_document_controller as cli_document_controller
from forte.controller.cli_document_controller import CliDocumentController
from forte.model.document import Document, DocumentNotFoundError
from forte.model.entity import Entity
from forte.model.entity_picker import EntityPickerAbortedError
from forte.model.vault import Vault, VaultContext


class _FakeVaultService:
    """Stands in for VaultService: always resolves to a single fake vault."""

    def resolve_vault(self, vault_name: str | None) -> Vault:
        return Vault(name=vault_name or "default", path=Path("/fake/vault"))


class _FakeDocumentService:
    """Stands in for DocumentService, scripted with a document, an entity
    catalog (for the "no entities" guard), a `link_document_interactive`
    result/error, and the current linked-entities state (for the abort
    case)."""

    def __init__(
        self,
        document: Document | None = None,
        all_entities: list[Entity] | None = None,
        link_result: list[Entity] | None = None,
        link_error: Exception | None = None,
        linked_entities: list[Entity] | None = None,
    ):
        self.document = document
        self.all_entities = all_entities if all_entities is not None else [_entity(1, "Alice")]
        self.link_result = link_result if link_result is not None else []
        self.link_error = link_error
        self.linked_entities = linked_entities if linked_entities is not None else []
        self.link_calls: list[int] = []

    def get_document(self, id: int) -> Document:
        if self.document is None:
            raise DocumentNotFoundError(f"Document #{id} does not exist.")
        return self.document

    def search_entities(self, query: str) -> list[Entity]:
        return self.all_entities

    def link_document_interactive(self, document_id: int) -> list[Entity]:
        self.link_calls.append(document_id)
        if self.link_error is not None:
            raise self.link_error
        return self.link_result

    def list_linked_entities(self, id: int) -> list[Entity]:
        return self.linked_entities


def _document(id: int, name: str) -> Document:
    return Document(
        id=id,
        name=name,
        source_path=f"/src/{name}.md",
        content_hash="abc123",
        ingested_at="2026-08-11T00:00:00",
        status="processed",
    )


def _entity(id: int, name: str, schema: str = "person") -> Entity:
    return Entity(id=id, schema=schema, name=name, aliases=[], fields={})


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


def _invoke_tty(main, args, isatty: bool = True):
    """Invoke the CLI, replacing the `sys` name bound inside the controller
    module with a stand-in whose `stdin.isatty()` returns `isatty`. Needed
    because `CliRunner.invoke` always substitutes its own (never-a-TTY)
    stdin for the real `sys.stdin` during the call, so patching the real
    `sys.stdin` beforehand has no effect."""
    runner = CliRunner()
    with pytest.MonkeyPatch.context() as mp:
        fake_sys = SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: isatty))
        mp.setattr(cli_document_controller, "sys", fake_sys)
        return runner.invoke(main, args)


def test_link_interactive_prints_linked_entities():
    document = _document(12, "Acme Kickoff Notes")
    linked = [_entity(1, "Alice"), _entity(4, "Acme Corp", schema="client")]
    service = _FakeDocumentService(document=document, link_result=linked)
    main = _cli(service)

    result = _invoke_tty(main, ["doc", "link-interactive", "12"])

    assert result.exit_code == 0, result.output
    assert "doc #12: Acme Kickoff Notes" in result.output
    assert "Linked 2 entities to doc #12: Acme Kickoff Notes" in result.output
    assert "#1 [person] Alice" in result.output
    assert "#4 [client] Acme Corp" in result.output
    assert service.link_calls == [12]


def test_link_interactive_no_links_prints_note():
    document = _document(12, "Acme Kickoff Notes")
    service = _FakeDocumentService(document=document, link_result=[])
    main = _cli(service)

    result = _invoke_tty(main, ["doc", "link-interactive", "12"])

    assert result.exit_code == 0, result.output
    assert "No entities linked to doc #12: Acme Kickoff Notes" in result.output


def test_link_interactive_non_tty_fails_fast_pointing_at_doc_link():
    document = _document(12, "Acme Kickoff Notes")
    service = _FakeDocumentService(document=document)
    main = _cli(service)

    result = _invoke_tty(main, ["doc", "link-interactive", "12"], isatty=False)

    assert result.exit_code != 0
    assert "forte doc link" in result.output
    # No prompt/session was attempted.
    assert service.link_calls == []


def test_link_interactive_no_entities_in_vault():
    document = _document(12, "Acme Kickoff Notes")
    service = _FakeDocumentService(document=document, all_entities=[])
    main = _cli(service)

    result = _invoke_tty(main, ["doc", "link-interactive", "12"])

    assert result.exit_code == 0, result.output
    assert "no entities to link" in result.output.lower()
    assert service.link_calls == []


def test_link_interactive_unknown_document_id_fails_before_prompt():
    service = _FakeDocumentService(document=None)
    main = _cli(service)

    result = _invoke_tty(main, ["doc", "link-interactive", "99"])

    assert result.exit_code != 0
    assert "99" in result.output
    assert service.link_calls == []
    # No "doc #..." header was printed since the document lookup failed first.
    assert "doc #99" not in result.output


def test_link_interactive_abort_reports_partial_progress():
    document = _document(12, "Acme Kickoff Notes")
    already_linked = [_entity(1, "Alice")]
    service = _FakeDocumentService(
        document=document,
        link_error=EntityPickerAbortedError("aborted"),
        linked_entities=already_linked,
    )
    main = _cli(service)

    result = _invoke_tty(main, ["doc", "link-interactive", "12"])

    assert result.exit_code != 0
    assert "Aborted" in result.output
    assert "#1 [person] Alice" in result.output
    assert "Traceback" not in result.output


def test_link_interactive_abort_with_nothing_linked():
    document = _document(12, "Acme Kickoff Notes")
    service = _FakeDocumentService(
        document=document,
        link_error=EntityPickerAbortedError("aborted"),
        linked_entities=[],
    )
    main = _cli(service)

    result = _invoke_tty(main, ["doc", "link-interactive", "12"])

    assert result.exit_code != 0
    assert "Aborted" in result.output
    assert "No entities were linked" in result.output
    assert "Traceback" not in result.output

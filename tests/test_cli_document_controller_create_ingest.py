"""Unit tests for the follow-on interactive link step offered by
`forte doc create` and `forte doc ingest`.

Per the style guide, controllers are tested with a real user interface
(`click.testing.CliRunner`) driving the actual `click.Group`, but a fake
`DocumentService` standing in for the real one - so these tests only verify
that `create`/`ingest` persist the document first, then delegate the link
step to the same guarded helper `link-interactive` uses (covered in depth by
`test_cli_document_controller_link_interactive.py`), plus the `--no-link`
and non-TTY-skip behavior specific to these two entry points.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

import forte.controller.cli_document_controller as cli_document_controller
from forte.controller.cli_document_controller import CliDocumentController
from forte.model.document import Document
from forte.model.entity import Entity
from forte.model.entity_picker import EntityPickerAbortedError
from forte.model.vault import Vault, VaultContext


class _FakeVaultService:
    """Stands in for VaultService: always resolves to a single fake vault."""

    def resolve_vault(self, vault_name: str | None) -> Vault:
        return Vault(name=vault_name or "default", path=Path("/fake/vault"))


class _FakeDocumentService:
    """Stands in for DocumentService, scripted with the document `create`/
    `ingest` should return, an entity catalog (for the "no entities" guard),
    a `link_document_interactive` result/error, and the current
    linked-entities state (for the abort case)."""

    def __init__(
        self,
        document: Document,
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
        self.create_calls: list[str] = []
        self.ingest_calls: list[Path] = []
        self.link_calls: list[int] = []

    def create_document(self, name: str) -> Document:
        self.create_calls.append(name)
        return self.document

    def ingest_document(self, path: Path, name: str | None = None) -> Document:
        self.ingest_calls.append(path)
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


# --- forte doc create ------------------------------------------------------


def test_create_offers_link_step_and_prints_summary():
    document = _document(12, "Kickoff Notes")
    linked = [_entity(1, "Alice")]
    service = _FakeDocumentService(document=document, link_result=linked)
    main = _cli(service)

    result = _invoke_tty(main, ["doc", "create", "Kickoff Notes"])

    assert result.exit_code == 0, result.output
    assert "Created doc #12: Kickoff Notes" in result.output
    assert "Linked 1 entity to doc #12: Kickoff Notes" in result.output
    assert "#1 [person] Alice" in result.output
    assert service.create_calls == ["Kickoff Notes"]
    assert service.link_calls == [12]


def test_create_no_link_skips_the_step():
    document = _document(12, "Kickoff Notes")
    service = _FakeDocumentService(document=document)
    main = _cli(service)

    result = _invoke_tty(main, ["doc", "create", "Kickoff Notes", "--no-link"])

    assert result.exit_code == 0, result.output
    assert "Created doc #12: Kickoff Notes" in result.output
    assert service.link_calls == []


def test_create_skips_link_step_when_stdin_not_tty():
    document = _document(12, "Kickoff Notes")
    service = _FakeDocumentService(document=document)
    main = _cli(service)

    result = _invoke_tty(main, ["doc", "create", "Kickoff Notes"], isatty=False)

    assert result.exit_code == 0, result.output
    assert "Created doc #12: Kickoff Notes" in result.output
    assert "not interactive" in result.output.lower()
    assert service.link_calls == []


def test_create_abort_reports_doc_id_and_resume_hint():
    document = _document(12, "Kickoff Notes")
    already_linked = [_entity(1, "Alice")]
    service = _FakeDocumentService(
        document=document,
        link_error=EntityPickerAbortedError("aborted"),
        linked_entities=already_linked,
    )
    main = _cli(service)

    result = _invoke_tty(main, ["doc", "create", "Kickoff Notes"])

    assert result.exit_code != 0
    assert "Created doc #12: Kickoff Notes" in result.output
    assert "Aborted" in result.output
    assert "#1 [person] Alice" in result.output
    assert "forte doc link-interactive 12" in result.output
    assert "Traceback" not in result.output


# --- forte doc ingest --------------------------------------------------------


def test_ingest_offers_link_step_and_prints_summary():
    document = _document(12, "kickoff.md")
    linked = [_entity(1, "Alice")]
    service = _FakeDocumentService(document=document, link_result=linked)
    main = _cli(service)

    result = _invoke_tty(main, ["doc", "ingest", "kickoff.md"])

    assert result.exit_code == 0, result.output
    assert "Ingested doc #12: kickoff.md" in result.output
    assert "Linked 1 entity to doc #12: kickoff.md" in result.output
    assert "#1 [person] Alice" in result.output
    assert service.link_calls == [12]


def test_ingest_no_link_skips_the_step():
    document = _document(12, "kickoff.md")
    service = _FakeDocumentService(document=document)
    main = _cli(service)

    result = _invoke_tty(main, ["doc", "ingest", "kickoff.md", "--no-link"])

    assert result.exit_code == 0, result.output
    assert "Ingested doc #12: kickoff.md" in result.output
    assert service.link_calls == []


def test_ingest_skips_link_step_when_stdin_not_tty():
    document = _document(12, "kickoff.md")
    service = _FakeDocumentService(document=document)
    main = _cli(service)

    result = _invoke_tty(main, ["doc", "ingest", "kickoff.md"], isatty=False)

    assert result.exit_code == 0, result.output
    assert "Ingested doc #12: kickoff.md" in result.output
    assert "not interactive" in result.output.lower()
    assert service.link_calls == []


def test_ingest_offers_link_step_for_deduped_document():
    # A dedup just means `ingest_document` returns the pre-existing document;
    # the controller has no special-casing to distinguish that from a fresh
    # ingest, so the link step still runs against that id.
    document = _document(7, "kickoff.md")
    linked = [_entity(1, "Alice")]
    service = _FakeDocumentService(document=document, link_result=linked)
    main = _cli(service)

    result = _invoke_tty(main, ["doc", "ingest", "kickoff.md"])

    assert result.exit_code == 0, result.output
    assert "Ingested doc #7: kickoff.md" in result.output
    assert service.link_calls == [7]


def test_ingest_abort_reports_doc_id_and_resume_hint():
    document = _document(12, "kickoff.md")
    already_linked = [_entity(1, "Alice")]
    service = _FakeDocumentService(
        document=document,
        link_error=EntityPickerAbortedError("aborted"),
        linked_entities=already_linked,
    )
    main = _cli(service)

    result = _invoke_tty(main, ["doc", "ingest", "kickoff.md"])

    assert result.exit_code != 0
    assert "Ingested doc #12: kickoff.md" in result.output
    assert "Aborted" in result.output
    assert "#1 [person] Alice" in result.output
    assert "forte doc link-interactive 12" in result.output
    assert "Traceback" not in result.output

"""Integration tests for CliDocumentController's `doc` Click command group.

These drive the new 3-layer document stack (CliDocumentController ->
DocumentService -> SqliteDocumentDb/SqliteMentionDb/SqliteEntityDb) directly,
since it is not yet wired into the top-level `forte` CLI (see main.py).
"""

from __future__ import annotations

from pathlib import Path

import click
from click.testing import CliRunner

from forte.client.fs_vault_fs import LocalVaultFs
from forte.client.sqlite_document_db import SqliteDocumentDb
from forte.client.sqlite_entity_db import SqliteEntityDb
from forte.client.sqlite_mention_db import SqliteMentionDb
from forte.client.sqlite_schema_db import SqliteSchemaDb
from forte.controller.cli_document_controller import CliDocumentController
from forte.controller.cli_entity_controller import CliEntityController
from forte.controller.cli_init_controller import CliInitController
from forte.controller.cli_schema_controller import CliSchemaController
from forte.service.document_service import DocumentService
from forte.service.entity_service import EntityService
from forte.service.init_service import InitService
from forte.service.schema_service import SchemaService


def _cli() -> click.Group:
    """Build a standalone `main` Click group with init/schema/entity/doc wired up."""

    @click.group()
    def main() -> None:
        pass

    init_service = InitService(LocalVaultFs())
    main.add_command(CliInitController(init_service).command())

    schema_db = SqliteSchemaDb()
    schema_service = SchemaService(schema_db)
    main.add_command(CliSchemaController(schema_service).group())

    entity_db = SqliteEntityDb()
    entity_service = EntityService(entity_db, schema_db)
    main.add_command(CliEntityController(entity_service).group())

    document_db = SqliteDocumentDb()
    mention_db = SqliteMentionDb()
    document_service = DocumentService(document_db, mention_db, entity_db)
    main.add_command(CliDocumentController(document_service).group())

    return main


def _init_vault(runner: CliRunner, main: click.Group) -> None:
    result = runner.invoke(main, ["init"])
    assert result.exit_code == 0, result.output


def _add_person_entity(runner: CliRunner, main: click.Group) -> None:
    result = runner.invoke(main, ["schema", "add", "person"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(main, ["entity", "add", "person", "--name", "Alice"])
    assert result.exit_code == 0, result.output


# --- ingest ----------------------------------------------------------------------


def test_ingest_happy_path() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        Path("note.md").write_text("# Hello\n\nSome content.\n")

        result = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert result.exit_code == 0, result.output
        assert "#1" in result.output
        assert "note.md" in result.output


def test_ingest_with_explicit_name() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        Path("note.md").write_text("# Hello\n\nSome content.\n")

        result = runner.invoke(main, ["doc", "ingest", "note.md", "--name", "Kickoff Notes"])
        assert result.exit_code == 0, result.output
        assert "Kickoff Notes" in result.output


def test_ingest_twice_is_idempotent() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        Path("note.md").write_text("# Hello\n\nSome content.\n")

        first = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert first.exit_code == 0, first.output
        second = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert second.exit_code == 0, second.output
        assert "#1" in first.output
        assert "#1" in second.output


def test_ingest_nonexistent_path_errors() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)

        result = runner.invoke(main, ["doc", "ingest", "missing.md"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()


def test_ingest_outside_vault_errors() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("note.md").write_text("# Hello\n")

        result = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert result.exit_code != 0
        assert "Not inside a Forte vault" in result.output


# --- list ------------------------------------------------------------------------


def test_list_shows_ingested_documents() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        Path("note1.md").write_text("# Hello\n")
        Path("note2.md").write_text("# World\n")

        runner.invoke(main, ["doc", "ingest", "note1.md"])
        runner.invoke(main, ["doc", "ingest", "note2.md"])

        result = runner.invoke(main, ["doc", "list"])
        assert result.exit_code == 0, result.output
        assert "#1" in result.output and "note1.md" in result.output
        assert "#2" in result.output and "note2.md" in result.output


def test_list_empty_vault() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)

        result = runner.invoke(main, ["doc", "list"])
        assert result.exit_code == 0, result.output
        assert "No documents yet." in result.output


# --- show ------------------------------------------------------------------------


def test_show_displays_doc_details() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        Path("note.md").write_text("# Hello\n\nSome unique content here.\n")

        runner.invoke(main, ["doc", "ingest", "note.md"])

        result = runner.invoke(main, ["doc", "show", "1"])
        assert result.exit_code == 0, result.output
        assert "note.md" in result.output


def test_show_nonexistent_id_errors() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)

        result = runner.invoke(main, ["doc", "show", "999"])
        assert result.exit_code != 0
        assert "not" in result.output.lower()


# --- link / unlink -----------------------------------------------------------------


def test_link_happy_path() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        Path("note.md").write_text("# Hello\n")
        runner.invoke(main, ["doc", "ingest", "note.md"])
        _add_person_entity(runner, main)

        result = runner.invoke(main, ["doc", "link", "1", "1"])
        assert result.exit_code == 0, result.output
        assert "Linked doc #1 to entity #1" in result.output


def test_link_nonexistent_doc_errors() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        _add_person_entity(runner, main)

        result = runner.invoke(main, ["doc", "link", "999", "1"])
        assert result.exit_code != 0
        assert "not" in result.output.lower()


def test_link_nonexistent_entity_errors() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        Path("note.md").write_text("# Hello\n")
        runner.invoke(main, ["doc", "ingest", "note.md"])

        result = runner.invoke(main, ["doc", "link", "1", "999"])
        assert result.exit_code != 0
        assert "not" in result.output.lower()


def test_link_twice_is_idempotent() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        Path("note.md").write_text("# Hello\n")
        runner.invoke(main, ["doc", "ingest", "note.md"])
        _add_person_entity(runner, main)

        first = runner.invoke(main, ["doc", "link", "1", "1"])
        assert first.exit_code == 0, first.output
        second = runner.invoke(main, ["doc", "link", "1", "1"])
        assert second.exit_code == 0, second.output


def test_unlink_happy_path() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        Path("note.md").write_text("# Hello\n")
        runner.invoke(main, ["doc", "ingest", "note.md"])
        _add_person_entity(runner, main)
        runner.invoke(main, ["doc", "link", "1", "1"])

        result = runner.invoke(main, ["doc", "unlink", "1", "1"])
        assert result.exit_code == 0, result.output
        assert "Unlinked doc #1 from entity #1" in result.output


def test_unlink_never_linked_is_noop_success() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        Path("note.md").write_text("# Hello\n")
        runner.invoke(main, ["doc", "ingest", "note.md"])
        _add_person_entity(runner, main)

        result = runner.invoke(main, ["doc", "unlink", "1", "1"])
        assert result.exit_code == 0, result.output
        assert "Unlinked doc #1 from entity #1" in result.output


def test_unlink_nonexistent_doc_errors() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        _add_person_entity(runner, main)

        result = runner.invoke(main, ["doc", "unlink", "999", "1"])
        assert result.exit_code != 0
        assert "not" in result.output.lower()


def test_unlink_nonexistent_entity_errors() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        Path("note.md").write_text("# Hello\n")
        runner.invoke(main, ["doc", "ingest", "note.md"])

        result = runner.invoke(main, ["doc", "unlink", "1", "999"])
        assert result.exit_code != 0
        assert "not" in result.output.lower()


# --- remove ----------------------------------------------------------------------


def test_remove_with_yes_removes_everywhere() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        _init_vault(runner, main)
        Path("note.md").write_text("# Hello\n")
        runner.invoke(main, ["doc", "ingest", "note.md"])

        raw_files = list((root / "docs" / "raw").iterdir())
        processed_files = list((root / "docs" / "processed").iterdir())
        assert len(raw_files) == 1
        assert len(processed_files) == 1

        result = runner.invoke(main, ["doc", "remove", "1", "--yes"])
        assert result.exit_code == 0, result.output
        assert "Removed doc #1: note.md" in result.output

        assert not raw_files[0].exists()
        assert not processed_files[0].exists()

        shown = runner.invoke(main, ["doc", "show", "1"])
        assert shown.exit_code != 0


def test_remove_doc_with_mentions_leaves_entity_intact() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        Path("note.md").write_text("# Hello\n")
        runner.invoke(main, ["doc", "ingest", "note.md"])
        _add_person_entity(runner, main)
        runner.invoke(main, ["doc", "link", "1", "1"])

        result = runner.invoke(main, ["doc", "remove", "1", "--yes"])
        assert result.exit_code == 0, result.output

        shown_doc = runner.invoke(main, ["doc", "show", "1"])
        assert shown_doc.exit_code != 0

        shown_entity = runner.invoke(main, ["entity", "show", "1"])
        assert shown_entity.exit_code == 0, shown_entity.output
        assert "Alice" in shown_entity.output


def test_remove_unknown_id_errors() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)

        result = runner.invoke(main, ["doc", "remove", "999", "--yes"])
        assert result.exit_code != 0
        assert "not" in result.output.lower()


def test_remove_prompt_aborted_on_no() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        Path("note.md").write_text("# Hello\n")
        runner.invoke(main, ["doc", "ingest", "note.md"])

        result = runner.invoke(main, ["doc", "remove", "1"], input="n\n")
        assert result.exit_code == 0, result.output
        assert "Aborted" in result.output

        shown = runner.invoke(main, ["doc", "show", "1"])
        assert shown.exit_code == 0, shown.output


def test_remove_prompt_confirmed_on_yes() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        Path("note.md").write_text("# Hello\n")
        runner.invoke(main, ["doc", "ingest", "note.md"])

        result = runner.invoke(main, ["doc", "remove", "1"], input="y\n")
        assert result.exit_code == 0, result.output
        assert "Removed doc #1: note.md" in result.output

        shown = runner.invoke(main, ["doc", "show", "1"])
        assert shown.exit_code != 0


# --- outside a vault ---------------------------------------------------------------


def test_link_outside_vault_errors() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["doc", "link", "1", "1"])
        assert result.exit_code != 0
        assert "Not inside a Forte vault" in result.output

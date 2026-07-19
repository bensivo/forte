"""Integration tests for the `forte doc` CLI command group."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from forte.cli import main
from forte.services.discovery import find_vault_root
from forte.services.document import link_document


def _init_vault(runner: CliRunner) -> None:
    result = runner.invoke(main, ["init"])
    assert result.exit_code == 0, result.output


def test_ingest_happy_path() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        Path("note.md").write_text("# Hello\n\nSome content.\n")

        result = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert result.exit_code == 0, result.output
        assert "#1" in result.output
        assert "note.md" in result.output


def test_ingest_defaults_name_to_filename() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        Path("note.md").write_text("# Hello\n\nSome content.\n")

        result = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert result.exit_code == 0, result.output
        assert "note.md" in result.output

        listed = runner.invoke(main, ["doc", "list"])
        assert "note.md" in listed.output

        shown = runner.invoke(main, ["doc", "show", "1"])
        assert "note.md" in shown.output


def test_ingest_with_explicit_name() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        Path("note.md").write_text("# Hello\n\nSome content.\n")

        result = runner.invoke(
            main, ["doc", "ingest", "note.md", "--name", "Kickoff Notes"]
        )
        assert result.exit_code == 0, result.output
        assert "Kickoff Notes" in result.output

        listed = runner.invoke(main, ["doc", "list"])
        assert "Kickoff Notes" in listed.output

        shown = runner.invoke(main, ["doc", "show", "1"])
        assert "Kickoff Notes" in shown.output


def test_ingest_twice_is_idempotent() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        Path("note.md").write_text("# Hello\n\nSome content.\n")

        first = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert first.exit_code == 0, first.output

        second = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert second.exit_code == 0, second.output

        assert "#1" in first.output
        assert "#1" in second.output


def test_ingest_nonexistent_path_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        result = runner.invoke(main, ["doc", "ingest", "missing.md"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()


def test_ingest_outside_vault_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("note.md").write_text("# Hello\n")

        result = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert result.exit_code != 0
        assert "Not inside a Forte vault" in result.output


def test_list_shows_ingested_documents() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        Path("note1.md").write_text("# Hello\n\nSome content.\n")
        Path("note2.md").write_text("# World\n\nMore content.\n")

        first = runner.invoke(main, ["doc", "ingest", "note1.md"])
        assert first.exit_code == 0, first.output
        second = runner.invoke(main, ["doc", "ingest", "note2.md"])
        assert second.exit_code == 0, second.output

        result = runner.invoke(main, ["doc", "list"])
        assert result.exit_code == 0, result.output
        assert "#1" in result.output
        assert "note1.md" in result.output
        assert "#2" in result.output
        assert "note2.md" in result.output


def test_list_empty_vault() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        result = runner.invoke(main, ["doc", "list"])
        assert result.exit_code == 0, result.output
        assert "No documents yet." in result.output


def test_show_displays_doc_details() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        Path("note.md").write_text("# Hello\n\nSome unique content here.\n")

        ingest = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert ingest.exit_code == 0, ingest.output

        result = runner.invoke(main, ["doc", "show", "1"])
        assert result.exit_code == 0, result.output
        assert "note.md" in result.output
        assert "Some unique content here." in result.output
        assert "Mentions: (none)" in result.output


def test_show_nonexistent_id_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        result = runner.invoke(main, ["doc", "show", "999"])
        assert result.exit_code != 0
        assert "not" in result.output.lower()


def test_show_displays_linked_entities() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        Path("note.md").write_text("# Hello\n\nSome content.\n")
        ingest = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert ingest.exit_code == 0, ingest.output

        schema_result = runner.invoke(main, ["schema", "add", "person"])
        assert schema_result.exit_code == 0, schema_result.output

        entity_result = runner.invoke(
            main, ["entity", "add", "person", "--name", "Alice"]
        )
        assert entity_result.exit_code == 0, entity_result.output

        root = find_vault_root(Path.cwd())
        link_document(root, 1, 1)

        result = runner.invoke(main, ["doc", "show", "1"])
        assert result.exit_code == 0, result.output
        assert "Mentions:" in result.output
        assert "entity #1" in result.output
        assert "Alice" in result.output


def test_link_happy_path() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        Path("note.md").write_text("# Hello\n\nSome content.\n")
        ingest = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert ingest.exit_code == 0, ingest.output

        schema_result = runner.invoke(main, ["schema", "add", "person"])
        assert schema_result.exit_code == 0, schema_result.output

        entity_result = runner.invoke(
            main, ["entity", "add", "person", "--name", "Alice"]
        )
        assert entity_result.exit_code == 0, entity_result.output

        result = runner.invoke(main, ["doc", "link", "1", "1"])
        assert result.exit_code == 0, result.output
        assert "Linked doc #1 to entity #1" in result.output

        show = runner.invoke(main, ["doc", "show", "1"])
        assert show.exit_code == 0, show.output
        assert "entity #1" in show.output
        assert "Alice" in show.output


def test_link_nonexistent_doc_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        schema_result = runner.invoke(main, ["schema", "add", "person"])
        assert schema_result.exit_code == 0, schema_result.output
        entity_result = runner.invoke(
            main, ["entity", "add", "person", "--name", "Alice"]
        )
        assert entity_result.exit_code == 0, entity_result.output

        result = runner.invoke(main, ["doc", "link", "999", "1"])
        assert result.exit_code != 0
        assert "not" in result.output.lower()


def test_link_nonexistent_entity_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        Path("note.md").write_text("# Hello\n\nSome content.\n")
        ingest = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert ingest.exit_code == 0, ingest.output

        result = runner.invoke(main, ["doc", "link", "1", "999"])
        assert result.exit_code != 0
        assert "not" in result.output.lower()


def test_link_twice_is_idempotent() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        Path("note.md").write_text("# Hello\n\nSome content.\n")
        ingest = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert ingest.exit_code == 0, ingest.output

        schema_result = runner.invoke(main, ["schema", "add", "person"])
        assert schema_result.exit_code == 0, schema_result.output
        entity_result = runner.invoke(
            main, ["entity", "add", "person", "--name", "Alice"]
        )
        assert entity_result.exit_code == 0, entity_result.output

        first = runner.invoke(main, ["doc", "link", "1", "1"])
        assert first.exit_code == 0, first.output
        second = runner.invoke(main, ["doc", "link", "1", "1"])
        assert second.exit_code == 0, second.output

        show = runner.invoke(main, ["doc", "show", "1"])
        assert show.exit_code == 0, show.output
        assert show.output.count("entity #1") == 1


def test_unlink_happy_path() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        Path("note.md").write_text("# Hello\n\nSome content.\n")
        ingest = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert ingest.exit_code == 0, ingest.output

        schema_result = runner.invoke(main, ["schema", "add", "person"])
        assert schema_result.exit_code == 0, schema_result.output

        entity_result = runner.invoke(
            main, ["entity", "add", "person", "--name", "Alice"]
        )
        assert entity_result.exit_code == 0, entity_result.output

        link = runner.invoke(main, ["doc", "link", "1", "1"])
        assert link.exit_code == 0, link.output

        result = runner.invoke(main, ["doc", "unlink", "1", "1"])
        assert result.exit_code == 0, result.output
        assert "Unlinked doc #1 from entity #1" in result.output

        show = runner.invoke(main, ["doc", "show", "1"])
        assert show.exit_code == 0, show.output
        assert "Mentions: (none)" in show.output
        assert "entity #1" not in show.output


def test_unlink_nonexistent_doc_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        schema_result = runner.invoke(main, ["schema", "add", "person"])
        assert schema_result.exit_code == 0, schema_result.output
        entity_result = runner.invoke(
            main, ["entity", "add", "person", "--name", "Alice"]
        )
        assert entity_result.exit_code == 0, entity_result.output

        result = runner.invoke(main, ["doc", "unlink", "999", "1"])
        assert result.exit_code != 0
        assert "not" in result.output.lower()


def test_unlink_nonexistent_entity_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        Path("note.md").write_text("# Hello\n\nSome content.\n")
        ingest = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert ingest.exit_code == 0, ingest.output

        result = runner.invoke(main, ["doc", "unlink", "1", "999"])
        assert result.exit_code != 0
        assert "not" in result.output.lower()


def test_unlink_never_linked_is_noop_success() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        Path("note.md").write_text("# Hello\n\nSome content.\n")
        ingest = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert ingest.exit_code == 0, ingest.output

        schema_result = runner.invoke(main, ["schema", "add", "person"])
        assert schema_result.exit_code == 0, schema_result.output
        entity_result = runner.invoke(
            main, ["entity", "add", "person", "--name", "Alice"]
        )
        assert entity_result.exit_code == 0, entity_result.output

        result = runner.invoke(main, ["doc", "unlink", "1", "1"])
        assert result.exit_code == 0, result.output
        assert "Unlinked doc #1 from entity #1" in result.output

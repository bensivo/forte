"""Integration tests for the `forte schema` CLI command group."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from click.testing import CliRunner

from forte.cli import main


def _init_vault(runner: CliRunner) -> None:
    result = runner.invoke(main, ["init"])
    assert result.exit_code == 0, result.output


def _schema_rows(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM schemas").fetchall()
    return {r[0] for r in rows}


def test_add_schema_with_fields_appears_in_list() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        _init_vault(runner)

        result = runner.invoke(
            main, ["schema", "add", "person", "--field", "employer", "--field", "role"]
        )
        assert result.exit_code == 0, result.output
        assert "person" in result.output
        assert "employer" in result.output
        assert "role" in result.output

        assert (Path(tmp) / "entities" / "person").is_dir()

        listed = runner.invoke(main, ["schema", "list"])
        assert listed.exit_code == 0, listed.output
        assert "person" in listed.output
        assert "employer" in listed.output
        assert "role" in listed.output


def test_add_schema_with_no_fields_succeeds() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        _init_vault(runner)

        result = runner.invoke(main, ["schema", "add", "note"])
        assert result.exit_code == 0, result.output
        assert "note" in result.output

        assert (Path(tmp) / "entities" / "note").is_dir()

        listed = runner.invoke(main, ["schema", "list"])
        assert listed.exit_code == 0, listed.output
        assert "note" in listed.output


def test_add_existing_schema_errors_and_leaves_original() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        first = runner.invoke(
            main, ["schema", "add", "person", "--field", "employer", "--field", "role"]
        )
        assert first.exit_code == 0, first.output

        dup = runner.invoke(main, ["schema", "add", "person", "--field", "email"])
        assert dup.exit_code != 0
        assert "already exists" in dup.output

        listed = runner.invoke(main, ["schema", "list"])
        assert "employer" in listed.output
        assert "role" in listed.output
        assert "email" not in listed.output


def test_add_rejects_reserved_field_name() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        _init_vault(runner)

        result = runner.invoke(main, ["schema", "add", "person", "--field", "name"])
        assert result.exit_code != 0
        assert "name" in result.output
        assert not (Path(tmp) / "entities" / "person").exists()


def test_add_rejects_reserved_field_aliases() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        _init_vault(runner)

        result = runner.invoke(main, ["schema", "add", "person", "--field", "aliases"])
        assert result.exit_code != 0
        assert "aliases" in result.output
        assert not (Path(tmp) / "entities" / "person").exists()


def test_add_rejects_duplicate_fields() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        _init_vault(runner)

        result = runner.invoke(
            main, ["schema", "add", "person", "--field", "role", "--field", "role"]
        )
        assert result.exit_code != 0
        assert "uplicate" in result.output
        assert not (Path(tmp) / "entities" / "person").exists()


def test_add_rejects_invalid_name() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        _init_vault(runner)

        result = runner.invoke(main, ["schema", "add", "My Schema"])
        assert result.exit_code != 0
        assert "Invalid schema name" in result.output
        assert not (Path(tmp) / "entities" / "My Schema").exists()


def test_list_with_several_schemas() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        runner.invoke(
            main, ["schema", "add", "person", "--field", "employer", "--field", "role"]
        )
        runner.invoke(
            main, ["schema", "add", "project", "--field", "status", "--field", "owner"]
        )

        listed = runner.invoke(main, ["schema", "list"])
        assert listed.exit_code == 0, listed.output
        for token in ("person", "employer", "role", "project", "status", "owner"):
            assert token in listed.output


def test_list_empty_vault_shows_friendly_message() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        listed = runner.invoke(main, ["schema", "list"])
        assert listed.exit_code == 0, listed.output
        assert "No schemas defined yet." in listed.output


def test_remove_with_yes_removes_everywhere() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        _init_vault(runner)
        root = Path(tmp)

        runner.invoke(main, ["schema", "add", "person", "--field", "role"])
        assert (root / "entities" / "person").is_dir()

        result = runner.invoke(main, ["schema", "remove", "person", "--yes"])
        assert result.exit_code == 0, result.output
        assert "Removed schema 'person'." in result.output

        # Gone from the list.
        listed = runner.invoke(main, ["schema", "list"])
        assert "person" not in listed.output

        # Gone from the entities folder.
        assert not (root / "entities" / "person").exists()

        # Gone from the DB.
        assert "person" not in _schema_rows(root / ".forte" / "index.db")


def test_remove_nonexistent_schema_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        result = runner.invoke(main, ["schema", "remove", "ghost", "--yes"])
        assert result.exit_code != 0
        assert "does not exist" in result.output


def test_schema_add_outside_vault_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["schema", "add", "person"])
        assert result.exit_code != 0
        assert "Not inside a Forte vault" in result.output


def test_schema_list_outside_vault_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["schema", "list"])
        assert result.exit_code != 0
        assert "Not inside a Forte vault" in result.output


def test_schema_remove_outside_vault_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["schema", "remove", "person", "--yes"])
        assert result.exit_code != 0
        assert "Not inside a Forte vault" in result.output

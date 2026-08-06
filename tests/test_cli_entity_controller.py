"""Integration tests for CliEntityController's `entity` Click command group.

These drive the new 3-layer entity stack (CliEntityController ->
EntityService -> SqliteEntityDb/SqliteSchemaDb) directly, since it is not yet
wired into the top-level `forte` CLI (see main.py).
"""

from __future__ import annotations

from pathlib import Path

import click
from click.testing import CliRunner

from forte.client.sqlite_entity_db import SqliteEntityDb
from forte.client.sqlite_schema_db import SqliteSchemaDb
from forte.controller.cli_entity_controller import CliEntityController
from forte.controller.cli_schema_controller import CliSchemaController
from forte.controller.cli_init_controller import CliInitController
from forte.client.fs_vault_fs import LocalVaultFs
from forte.service.entity_service import EntityService
from forte.service.schema_service import SchemaService
from forte.service.init_service import InitService


def _cli() -> click.Group:
    """Build a standalone `main` Click group with init/schema/entity wired up."""

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

    return main


def _init_vault(runner: CliRunner, main: click.Group) -> None:
    result = runner.invoke(main, ["init"])
    assert result.exit_code == 0, result.output


def _add_person_schema(runner: CliRunner, main: click.Group) -> None:
    result = runner.invoke(
        main, ["schema", "add", "person", "--field", "employer", "--field", "role"]
    )
    assert result.exit_code == 0, result.output


# --- add -----------------------------------------------------------------------


def test_add_entity_happy_path() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        _add_person_schema(runner, main)

        result = runner.invoke(
            main,
            [
                "entity",
                "add",
                "person",
                "--name",
                "Ben Sivongxay",
                "--field",
                "employer=Acme",
                "--field",
                "role=Engineer",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Ben Sivongxay" in result.output
        assert "#1" in result.output

        listed = runner.invoke(main, ["entity", "list"])
        assert "Ben Sivongxay" in listed.output

        shown = runner.invoke(main, ["entity", "show", "1"])
        assert shown.exit_code == 0, shown.output
        assert "Acme" in shown.output
        assert "Engineer" in shown.output


def test_add_entity_unknown_schema_errors() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)

        result = runner.invoke(main, ["entity", "add", "person", "--name", "Ben"])
        assert result.exit_code != 0
        assert "does not exist" in result.output


def test_add_entity_unknown_field_errors() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        _add_person_schema(runner, main)

        result = runner.invoke(
            main, ["entity", "add", "person", "--name", "Ben", "--field", "height=tall"]
        )
        assert result.exit_code != 0
        assert "height" in result.output


# --- list ------------------------------------------------------------------------


def test_list_filtered_by_schema() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        _add_person_schema(runner, main)
        runner.invoke(main, ["schema", "add", "project", "--field", "status"])

        runner.invoke(main, ["entity", "add", "person", "--name", "Ben"])
        runner.invoke(main, ["entity", "add", "project", "--name", "Forte"])

        listed = runner.invoke(main, ["entity", "list", "--schema", "person"])
        assert listed.exit_code == 0, listed.output
        assert "Ben" in listed.output
        assert "Forte" not in listed.output


def test_list_empty_vault_friendly_message() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)

        listed = runner.invoke(main, ["entity", "list"])
        assert listed.exit_code == 0, listed.output
        assert "No entities yet." in listed.output


# --- edit ------------------------------------------------------------------------


def test_edit_set_field_and_add_alias() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        _add_person_schema(runner, main)
        runner.invoke(main, ["entity", "add", "person", "--name", "Ben"])

        result = runner.invoke(
            main,
            ["entity", "edit", "1", "--set", "role=Engineer", "--add-alias", "Ben S."],
        )
        assert result.exit_code == 0, result.output

        shown = runner.invoke(main, ["entity", "show", "1"])
        assert "Engineer" in shown.output
        assert "Ben S." in shown.output


def test_edit_not_found_errors() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)

        result = runner.invoke(main, ["entity", "edit", "999", "--name", "Whoever"])
        assert result.exit_code != 0
        assert "not exist" in result.output


# --- remove ----------------------------------------------------------------------


def test_remove_with_yes_removes_everywhere() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        _init_vault(runner, main)
        _add_person_schema(runner, main)
        runner.invoke(main, ["entity", "add", "person", "--name", "Ben"])

        result = runner.invoke(main, ["entity", "remove", "1", "--yes"])
        assert result.exit_code == 0, result.output
        assert "Removed" in result.output

        assert list((root / "entities").rglob("*.md")) == []

        shown = runner.invoke(main, ["entity", "show", "1"])
        assert shown.exit_code != 0


def test_remove_unknown_id_errors() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)

        result = runner.invoke(main, ["entity", "remove", "999", "--yes"])
        assert result.exit_code != 0
        assert "not exist" in result.output


# --- outside a vault ---------------------------------------------------------------


def test_add_outside_vault_errors() -> None:
    main = _cli()
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["entity", "add", "person", "--name", "Ben"])
        assert result.exit_code != 0
        assert "Not inside a Forte vault" in result.output

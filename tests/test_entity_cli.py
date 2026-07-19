"""Integration tests for the `forte entity` CLI command group."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from click.testing import CliRunner

from forte.cli import main


def _init_vault(runner: CliRunner) -> None:
    result = runner.invoke(main, ["init"])
    assert result.exit_code == 0, result.output


def _add_person_schema(runner: CliRunner) -> None:
    result = runner.invoke(
        main, ["schema", "add", "person", "--field", "employer", "--field", "role"]
    )
    assert result.exit_code == 0, result.output


def _add_project_schema(runner: CliRunner) -> None:
    result = runner.invoke(main, ["schema", "add", "project", "--field", "status"])
    assert result.exit_code == 0, result.output


def _entity_rows(db_path: Path) -> list[tuple]:
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT id, schema, name FROM entities ORDER BY id").fetchall()


def _md_files(root: Path) -> list[Path]:
    return list((root / "entities").rglob("*.md"))


# --- add ---------------------------------------------------------------------


def test_add_entity_happy_path() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        _init_vault(runner)
        _add_person_schema(runner)

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
        assert "person" in result.output
        assert "Ben Sivongxay" in result.output
        assert "#1" in result.output

        # Markdown file exists.
        files = _md_files(root)
        assert len(files) == 1
        content = files[0].read_text()
        assert "Ben Sivongxay" in content
        assert "Acme" in content
        assert "Engineer" in content

        # DB row present.
        rows = _entity_rows(root / ".forte" / "index.db")
        assert rows == [(1, "person", "Ben Sivongxay")]

        # Visible via list.
        listed = runner.invoke(main, ["entity", "list"])
        assert listed.exit_code == 0, listed.output
        assert "Ben Sivongxay" in listed.output

        # Visible via show with field values.
        shown = runner.invoke(main, ["entity", "show", "1"])
        assert shown.exit_code == 0, shown.output
        assert "Acme" in shown.output
        assert "Engineer" in shown.output


def test_add_entity_only_name_backfills_fields() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)
        _add_person_schema(runner)

        result = runner.invoke(main, ["entity", "add", "person", "--name", "Ben Sivongxay"])
        assert result.exit_code == 0, result.output

        shown = runner.invoke(main, ["entity", "show", "1"])
        assert shown.exit_code == 0, shown.output
        assert "employer" in shown.output
        assert "role" in shown.output


def test_add_entity_with_aliases() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)
        _add_person_schema(runner)

        result = runner.invoke(
            main,
            [
                "entity",
                "add",
                "person",
                "--name",
                "Ben Sivongxay",
                "--alias",
                "Ben",
                "--alias",
                "Ben S.",
            ],
        )
        assert result.exit_code == 0, result.output

        shown = runner.invoke(main, ["entity", "show", "1"])
        assert "Ben S." in shown.output


def test_add_entity_unknown_schema_errors_and_creates_nothing() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        _init_vault(runner)

        result = runner.invoke(main, ["entity", "add", "person", "--name", "Ben"])
        assert result.exit_code != 0
        assert "does not exist" in result.output

        assert _md_files(root) == []
        assert _entity_rows(root / ".forte" / "index.db") == []


def test_add_entity_missing_name_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)
        _add_person_schema(runner)

        result = runner.invoke(main, ["entity", "add", "person"])
        assert result.exit_code != 0


def test_add_entity_empty_name_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        _init_vault(runner)
        _add_person_schema(runner)

        result = runner.invoke(main, ["entity", "add", "person", "--name", ""])
        assert result.exit_code != 0
        assert _entity_rows(root / ".forte" / "index.db") == []


def test_add_entity_unknown_field_errors_and_creates_nothing() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        _init_vault(runner)
        _add_person_schema(runner)

        result = runner.invoke(
            main,
            ["entity", "add", "person", "--name", "Ben", "--field", "height=tall"],
        )
        assert result.exit_code != 0
        assert "height" in result.output

        assert _md_files(root) == []
        assert _entity_rows(root / ".forte" / "index.db") == []


def test_add_entity_malformed_field_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)
        _add_person_schema(runner)

        result = runner.invoke(
            main, ["entity", "add", "person", "--name", "Ben", "--field", "employer"]
        )
        assert result.exit_code != 0


# --- list --------------------------------------------------------------------


def test_list_across_two_schemas() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)
        _add_person_schema(runner)
        _add_project_schema(runner)

        runner.invoke(main, ["entity", "add", "person", "--name", "Ben"])
        runner.invoke(main, ["entity", "add", "project", "--name", "Forte"])

        listed = runner.invoke(main, ["entity", "list"])
        assert listed.exit_code == 0, listed.output
        assert "Ben" in listed.output
        assert "Forte" in listed.output
        assert "person" in listed.output
        assert "project" in listed.output


def test_list_filtered_by_schema() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)
        _add_person_schema(runner)
        _add_project_schema(runner)

        runner.invoke(main, ["entity", "add", "person", "--name", "Ben"])
        runner.invoke(main, ["entity", "add", "person", "--name", "Alice"])
        runner.invoke(main, ["entity", "add", "project", "--name", "Forte"])

        listed = runner.invoke(main, ["entity", "list", "--schema", "person"])
        assert listed.exit_code == 0, listed.output
        assert "Ben" in listed.output
        assert "Alice" in listed.output
        assert "Forte" not in listed.output


def test_list_unknown_schema_filter_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        listed = runner.invoke(main, ["entity", "list", "--schema", "widget"])
        assert listed.exit_code != 0
        assert "does not exist" in listed.output


def test_list_empty_vault_friendly_message() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        listed = runner.invoke(main, ["entity", "list"])
        assert listed.exit_code == 0, listed.output
        assert "No entities yet." in listed.output


# --- show --------------------------------------------------------------------


def test_show_happy_path() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)
        _add_person_schema(runner)

        runner.invoke(
            main,
            [
                "entity",
                "add",
                "person",
                "--name",
                "Ben Sivongxay",
                "--alias",
                "Ben",
                "--field",
                "employer=Acme",
                "--field",
                "role=Engineer",
            ],
        )

        shown = runner.invoke(main, ["entity", "show", "1"])
        assert shown.exit_code == 0, shown.output
        assert "Ben Sivongxay" in shown.output
        assert "person" in shown.output
        assert "Ben" in shown.output
        assert "employer" in shown.output
        assert "Acme" in shown.output
        assert "role" in shown.output
        assert "Engineer" in shown.output


def test_show_not_found_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        shown = runner.invoke(main, ["entity", "show", "999"])
        assert shown.exit_code != 0
        assert "not exist" in shown.output


# --- edit --------------------------------------------------------------------


def test_edit_set_field_and_add_alias_reflected_everywhere() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        _init_vault(runner)
        _add_person_schema(runner)

        runner.invoke(main, ["entity", "add", "person", "--name", "Ben"])

        result = runner.invoke(
            main,
            [
                "entity",
                "edit",
                "1",
                "--set",
                "role=Engineer",
                "--add-alias",
                "Ben S.",
            ],
        )
        assert result.exit_code == 0, result.output

        shown = runner.invoke(main, ["entity", "show", "1"])
        assert "Engineer" in shown.output
        assert "Ben S." in shown.output

        # On-disk markdown reflects the change.
        content = _md_files(root)[0].read_text()
        assert "Engineer" in content
        assert "Ben S." in content


def test_edit_unknown_field_errors_and_leaves_unchanged() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        _init_vault(runner)
        _add_person_schema(runner)

        runner.invoke(
            main,
            ["entity", "add", "person", "--name", "Ben", "--field", "role=Engineer"],
        )
        before = _md_files(root)[0].read_text()

        result = runner.invoke(main, ["entity", "edit", "1", "--set", "height=tall"])
        assert result.exit_code != 0
        assert "height" in result.output

        after = _md_files(root)[0].read_text()
        assert before == after


def test_edit_rename_updates_markdown_filename() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        _init_vault(runner)
        _add_person_schema(runner)

        runner.invoke(main, ["entity", "add", "person", "--name", "Ben Sivongxay"])
        old_files = _md_files(root)
        assert len(old_files) == 1
        old_path = old_files[0]

        result = runner.invoke(main, ["entity", "edit", "1", "--name", "Benjamin Sivongxay"])
        assert result.exit_code == 0, result.output

        files = _md_files(root)
        assert len(files) == 1
        assert files[0] != old_path
        assert not old_path.exists()
        assert "benjamin-sivongxay" in files[0].name


def test_edit_not_found_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        result = runner.invoke(main, ["entity", "edit", "999", "--name", "Whoever"])
        assert result.exit_code != 0
        assert "not exist" in result.output


# --- remove ------------------------------------------------------------------


def test_remove_with_yes_removes_everywhere() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        _init_vault(runner)
        _add_person_schema(runner)

        runner.invoke(main, ["entity", "add", "person", "--name", "Ben"])
        assert len(_md_files(root)) == 1

        result = runner.invoke(main, ["entity", "remove", "1", "--yes"])
        assert result.exit_code == 0, result.output
        assert "Removed" in result.output

        assert _md_files(root) == []
        assert _entity_rows(root / ".forte" / "index.db") == []

        shown = runner.invoke(main, ["entity", "show", "1"])
        assert shown.exit_code != 0


def test_remove_unknown_id_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        result = runner.invoke(main, ["entity", "remove", "999", "--yes"])
        assert result.exit_code != 0
        assert "not exist" in result.output


# --- outside a vault ---------------------------------------------------------


def test_add_outside_vault_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["entity", "add", "person", "--name", "Ben"])
        assert result.exit_code != 0
        assert "Not inside a Forte vault" in result.output


def test_list_outside_vault_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["entity", "list"])
        assert result.exit_code != 0
        assert "Not inside a Forte vault" in result.output


def test_show_outside_vault_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["entity", "show", "1"])
        assert result.exit_code != 0
        assert "Not inside a Forte vault" in result.output


def test_edit_outside_vault_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["entity", "edit", "1", "--name", "Ben"])
        assert result.exit_code != 0
        assert "Not inside a Forte vault" in result.output


def test_remove_outside_vault_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["entity", "remove", "1", "--yes"])
        assert result.exit_code != 0
        assert "Not inside a Forte vault" in result.output

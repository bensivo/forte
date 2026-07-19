"""Integration tests for the `forte init` CLI command."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from click.testing import CliRunner

from forte.cli import main

EXPECTED_TABLES = {
    "documents",
    "schemas",
    "entities",
    "entity_field_values",
    "mentions",
    "ingest_changes",
}


def _tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def test_init_in_empty_dir_creates_full_layout() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        result = runner.invoke(main, ["init"])
        assert result.exit_code == 0, result.output
        assert "Initialized Forte vault" in result.output

        root = Path(tmp)
        assert (root / ".forte").is_dir()
        assert (root / ".forte" / "config.yaml").is_file()
        assert (root / ".forte" / "config.yaml").stat().st_size > 0
        assert (root / "docs" / "raw").is_dir()
        assert (root / "docs" / "processed").is_dir()
        assert (root / "entities").is_dir()

        db_path = root / ".forte" / "index.db"
        assert db_path.is_file()
        assert EXPECTED_TABLES.issubset(_tables(db_path))


def test_init_fails_when_vault_already_exists() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        first = runner.invoke(main, ["init"])
        assert first.exit_code == 0, first.output

        config_path = Path(tmp) / ".forte" / "config.yaml"
        original_config = config_path.read_bytes()

        second = runner.invoke(main, ["init"])
        assert second.exit_code != 0
        assert "already exists" in second.output

        # Existing vault files must not be modified.
        assert config_path.read_bytes() == original_config


def test_init_succeeds_in_non_empty_dir_without_vault() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        pre_existing = root / "README.md"
        pre_existing.write_text("hello\n")
        (root / "notes.txt").write_text("stuff\n")

        result = runner.invoke(main, ["init"])
        assert result.exit_code == 0, result.output

        assert (root / ".forte" / "index.db").is_file()
        assert (root / "docs" / "raw").is_dir()
        assert (root / "entities").is_dir()
        # Pre-existing files untouched.
        assert pre_existing.read_text() == "hello\n"


def test_init_fails_when_docs_dir_already_present() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        (root / "docs").mkdir()
        (root / "docs" / "existing.md").write_text("keep me\n")

        result = runner.invoke(main, ["init"])
        assert result.exit_code != 0
        assert "docs/" in result.output
        assert "empty directory" in result.output

        # Nothing created, nothing touched.
        assert not (root / ".forte").exists()
        assert not (root / "entities").exists()
        assert (root / "docs" / "existing.md").read_text() == "keep me\n"


def test_init_fails_when_entities_dir_already_present() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        (root / "entities").mkdir()

        result = runner.invoke(main, ["init"])
        assert result.exit_code != 0
        assert "entities/" in result.output
        assert "empty directory" in result.output

        assert not (root / ".forte").exists()
        assert not (root / "docs").exists()

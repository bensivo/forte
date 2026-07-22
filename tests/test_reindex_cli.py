"""Integration tests for the `forte reindex` CLI command."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from forte.cli import main


def _init_vault(runner: CliRunner) -> None:
    result = runner.invoke(main, ["init"])
    assert result.exit_code == 0, result.output


def test_reindex_empty_vault_is_clean_noop() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        result = runner.invoke(main, ["reindex"])
        assert result.exit_code == 0, result.output
        assert "Reindexed" in result.output
        assert "0 entities" in result.output
        assert "0 documents" in result.output


def test_reindex_rebuilds_index_and_search_works_after() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        Path("note.md").write_text("Grace Hopper pioneered early compiler design.\n")
        ingest = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert ingest.exit_code == 0, ingest.output

        result = runner.invoke(main, ["reindex"])
        assert result.exit_code == 0, result.output
        assert "1 documents" in result.output

        search_result = runner.invoke(main, ["search", "compiler"])
        assert search_result.exit_code == 0, search_result.output
        assert "doc #1" in search_result.output


def test_reindex_outside_vault_fails() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["reindex"])
        assert result.exit_code != 0

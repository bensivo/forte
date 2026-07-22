"""Integration tests for the `forte search` CLI command."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from forte.cli import main
from forte.db.index_repository import IndexRepository
from forte.services.discovery import find_vault_root


def _init_vault(runner: CliRunner) -> None:
    result = runner.invoke(main, ["init"])
    assert result.exit_code == 0, result.output


def test_search_returns_ranked_results_with_score_and_source() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        Path("note.md").write_text("Ada Lovelace wrote the first computer algorithm.\n")
        ingest = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert ingest.exit_code == 0, ingest.output

        result = runner.invoke(main, ["search", "algorithm"])
        assert result.exit_code == 0, result.output
        assert "doc #1" in result.output
        assert "note.md" in result.output
        assert "[" in result.output  # score marker, e.g. "[0.123]"


def test_search_no_matches_prints_no_results() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        # An empty, never-indexed vault is otherwise "stale" (no index model
        # stamped yet); `forte reindex` on an empty vault is a clean no-op
        # that still stamps the model, matching the "empty vault" spec
        # scenario (see docs/spec/forte-search.md).
        reindex_result = runner.invoke(main, ["reindex"])
        assert reindex_result.exit_code == 0, reindex_result.output

        result = runner.invoke(main, ["search", "anything at all"])
        assert result.exit_code == 0, result.output
        assert "No results." in result.output


def test_search_outside_vault_fails() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["search", "query"])
        assert result.exit_code != 0


def test_search_stale_index_reports_reindex_hint() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        Path("note.md").write_text("Some searchable content about vector databases.\n")
        ingest = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert ingest.exit_code == 0, ingest.output

        root = find_vault_root(Path.cwd())
        IndexRepository(root).set_index_model("some-other-model")

        result = runner.invoke(main, ["search", "vector"])
        assert result.exit_code != 0
        assert "reindex" in result.output

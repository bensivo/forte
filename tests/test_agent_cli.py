"""Integration tests for the `forte agent` CLI command group."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

import forte.cli as forte_cli
from forte.cli import main
from forte.services.agent._llm import LLMResponse, StubLLMClient
from forte.services.agent._usage import Usage


def _init_vault(runner: CliRunner) -> None:
    result = runner.invoke(main, ["init"])
    assert result.exit_code == 0, result.output


def _resp(payload: dict, usage: Usage | None = None) -> LLMResponse:
    return LLMResponse(text=json.dumps(payload), usage=usage or Usage.zero())


def _stub_new_entity_with_field() -> StubLLMClient:
    """Extract one new-entity candidate, no resolve call (no existing entities), field-extract."""
    return StubLLMClient(
        [
            _resp(
                {
                    "entities": [
                        {
                            "name": "Ada Lovelace",
                            "schema": "person",
                            "supporting_quote": "Ada Lovelace wrote the first algorithm.",
                        }
                    ]
                },
                Usage(input_tokens=10, output_tokens=5),
            ),
            _resp(
                {"role": "Mathematician", "employer": ""},
                Usage(input_tokens=7, output_tokens=3),
            ),
        ]
    )


def test_process_happy_path_lands_entities_and_mentions(monkeypatch) -> None:
    stub = _stub_new_entity_with_field()
    monkeypatch.setattr(forte_cli, "_build_llm_client", lambda config: stub)

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)
        schema_result = runner.invoke(
            main, ["schema", "add", "person", "--field", "employer", "--field", "role"]
        )
        assert schema_result.exit_code == 0, schema_result.output

        Path("note.md").write_text("Ada Lovelace wrote the first algorithm.\n")
        ingest = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert ingest.exit_code == 0, ingest.output

        result = runner.invoke(main, ["agent", "process", "1", "--yes"])
        assert result.exit_code == 0, result.output
        assert "total:" in result.output

        listed = runner.invoke(main, ["entity", "list"])
        assert listed.exit_code == 0, listed.output
        assert "Ada Lovelace" in listed.output

        shown = runner.invoke(main, ["doc", "show", "1"])
        assert shown.exit_code == 0, shown.output
        assert "Mentions:" in shown.output
        assert "Ada Lovelace" in shown.output


def test_process_dry_run_writes_nothing(monkeypatch) -> None:
    stub = _stub_new_entity_with_field()
    monkeypatch.setattr(forte_cli, "_build_llm_client", lambda config: stub)

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)
        schema_result = runner.invoke(
            main, ["schema", "add", "person", "--field", "employer", "--field", "role"]
        )
        assert schema_result.exit_code == 0, schema_result.output

        Path("note.md").write_text("Ada Lovelace wrote the first algorithm.\n")
        ingest = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert ingest.exit_code == 0, ingest.output

        result = runner.invoke(main, ["agent", "process", "1", "--yes", "--dry-run"])
        assert result.exit_code == 0, result.output

        listed = runner.invoke(main, ["entity", "list"])
        assert listed.exit_code == 0, listed.output
        assert "No entities yet." in listed.output


def test_process_bad_doc_id_errors(monkeypatch) -> None:
    stub = StubLLMClient([])
    monkeypatch.setattr(forte_cli, "_build_llm_client", lambda config: stub)

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        result = runner.invoke(main, ["agent", "process", "999", "--yes"])
        assert result.exit_code != 0
        assert "not" in result.output.lower()


def test_process_outside_vault_errors() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["agent", "process", "1", "--yes"])
        assert result.exit_code != 0
        assert "Not inside a Forte vault" in result.output


def test_process_missing_api_key_errors(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)

        Path("note.md").write_text("Some text.\n")
        ingest = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert ingest.exit_code == 0, ingest.output

        result = runner.invoke(main, ["agent", "process", "1", "--yes"])
        assert result.exit_code != 0
        assert "api" in result.output.lower() or "key" in result.output.lower()


def test_ingest_ingests_and_processes_in_one_command(monkeypatch) -> None:
    stub = _stub_new_entity_with_field()
    monkeypatch.setattr(forte_cli, "_build_llm_client", lambda config: stub)

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner)
        schema_result = runner.invoke(
            main, ["schema", "add", "person", "--field", "employer", "--field", "role"]
        )
        assert schema_result.exit_code == 0, schema_result.output

        Path("kickoff.md").write_text("Ada Lovelace wrote the first algorithm.\n")

        result = runner.invoke(main, ["agent", "ingest", "kickoff.md", "--yes"])
        assert result.exit_code == 0, result.output
        assert "Ingested doc #1" in result.output

        listed = runner.invoke(main, ["entity", "list"])
        assert listed.exit_code == 0, listed.output
        assert "Ada Lovelace" in listed.output

        shown = runner.invoke(main, ["doc", "show", "1"])
        assert shown.exit_code == 0, shown.output
        assert "Mentions:" in shown.output

"""Integration tests for CliAgentController's `agent` Click command group.

These drive the new 3-layer agent stack (CliAgentController -> AgentService ->
the SQLite/markdown clients) against a throwaway vault, with the vault registry
pointed at a temp home directory so tests never read or write the real
`~/.forte/`. The LLM boundary and the editor session are always replaced via
the controller's `_build_llm_client` / `_build_editor_session` construction
seams, so no test needs an API key, makes a network call, or spawns an editor.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import click
from click.testing import CliRunner

from forte.client.fs_vault_fs import LocalVaultFs
from forte.client.sqlite_document_db import SqliteDocumentDb
from forte.client.sqlite_entity_db import SqliteEntityDb
from forte.client.sqlite_mention_db import SqliteMentionDb
from forte.client.sqlite_schema_db import SqliteSchemaDb
from forte.client.yaml_config_store import YamlConfigStore
from forte.client.yaml_vault_registry import YamlVaultRegistry
from forte.controller.cli_agent_controller import CliAgentController
from forte.controller.cli_document_controller import CliDocumentController
from forte.controller.cli_entity_controller import CliEntityController
from forte.controller.cli_schema_controller import CliSchemaController
from forte.controller.cli_vault_controller import CliVaultController
from forte.model.agent import EditorAbortedError
from forte.model.llm import LlmResponse, Usage
from forte.model.vault import VaultContext
from forte.service.agent_service import AgentService
from forte.service.config_service import ConfigService
from forte.service.document_service import DocumentService
from forte.service.entity_service import EntityService
from forte.service.schema_service import SchemaService
from forte.service.vault_service import VaultService
from tests.agent_stack import mentions_for_doc
from tests.fake_llm_client import StubLlmClient


def _cli() -> tuple[click.Group, CliAgentController]:
    """Build a standalone `main` group with vault/schema/entity/doc/agent wired up.

    Mirrors `forte.main`'s composition root, except the vault registry is
    pointed at a throwaway home directory. Returns the group plus the agent
    controller, so tests can monkeypatch its construction seams.
    """

    @click.group()
    def main() -> None:
        pass

    context = VaultContext()

    home_dir = Path(tempfile.mkdtemp())
    vault_service = VaultService(YamlVaultRegistry(home_dir=home_dir), LocalVaultFs())
    main.add_command(CliVaultController(vault_service).group())

    schema_db = SqliteSchemaDb(context)
    schema_service = SchemaService(schema_db)
    main.add_command(CliSchemaController(schema_service, vault_service, context).group())

    entity_db = SqliteEntityDb(context)
    entity_service = EntityService(entity_db, schema_db)
    main.add_command(CliEntityController(entity_service, vault_service, context).group())

    document_db = SqliteDocumentDb(context)
    mention_db = SqliteMentionDb(context)
    document_service = DocumentService(document_db, mention_db, entity_db)
    main.add_command(CliDocumentController(document_service, vault_service, context).group())

    config_service = ConfigService(YamlConfigStore(context))
    agent_service = AgentService(
        None, config_service, document_service, entity_service, schema_service
    )
    agent_controller = CliAgentController(
        agent_service, document_service, config_service, vault_service, context
    )
    main.add_command(agent_controller.group())

    return main, agent_controller


def _init_vault(runner: CliRunner, main: click.Group) -> None:
    """Create and register a vault in the current directory, as the default."""
    result = runner.invoke(main, ["vault", "create", "test", "."])
    assert result.exit_code == 0, result.output


def _add_person_schema(runner: CliRunner, main: click.Group) -> None:
    result = runner.invoke(
        main, ["schema", "add", "person", "--field", "employer", "--field", "role"]
    )
    assert result.exit_code == 0, result.output


def _resp(payload: dict, usage: Usage | None = None) -> LlmResponse:
    return LlmResponse(text=json.dumps(payload), usage=usage or Usage.zero())


def _stub_new_entity_with_field() -> StubLlmClient:
    """Extract one new-entity candidate, no resolve call (no existing entities), field-extract."""
    return StubLlmClient(
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


class ScriptedEditor:
    """EditorSession stub: applies a scripted ``str -> str`` transform.

    Records whether/how many times `edit` was invoked so tests can assert the
    editor was (or was never) opened.
    """

    def __init__(self, transform):
        self._transform = transform
        self.received: str | None = None
        self.calls = 0

    def edit(self, text: str) -> str:
        self.received = text
        self.calls += 1
        return self._transform(text)


def _unchanged(text: str) -> str:
    return text


def _abort_edit(_text: str):
    raise EditorAbortedError("user quit with :cq")


def _use_stub_llm(controller: CliAgentController, stub) -> None:
    controller._build_llm_client = lambda: stub


def _use_editor(controller: CliAgentController, editor) -> None:
    controller._build_editor_session = lambda: editor


# --- process ---------------------------------------------------------------------


def test_process_happy_path_lands_entities_and_mentions() -> None:
    main, controller = _cli()
    _use_stub_llm(controller, _stub_new_entity_with_field())

    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        _init_vault(runner, main)
        _add_person_schema(runner, main)

        Path("note.md").write_text("Ada Lovelace wrote the first algorithm.\n")
        ingest = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert ingest.exit_code == 0, ingest.output

        result = runner.invoke(main, ["agent", "process", "1", "--yes"])
        assert result.exit_code == 0, result.output
        assert "total:" in result.output

        listed = runner.invoke(main, ["entity", "list"])
        assert listed.exit_code == 0, listed.output
        assert "Ada Lovelace" in listed.output

        assert len(mentions_for_doc(Path(tmp), 1)) == 1


def test_process_dry_run_writes_nothing() -> None:
    main, controller = _cli()
    _use_stub_llm(controller, _stub_new_entity_with_field())

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        _add_person_schema(runner, main)

        Path("note.md").write_text("Ada Lovelace wrote the first algorithm.\n")
        runner.invoke(main, ["doc", "ingest", "note.md"])

        result = runner.invoke(main, ["agent", "process", "1", "--yes", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "Dry run" in result.output

        listed = runner.invoke(main, ["entity", "list"])
        assert listed.exit_code == 0, listed.output
        assert "No entities yet." in listed.output


def test_process_bad_doc_id_errors() -> None:
    main, controller = _cli()
    _use_stub_llm(controller, StubLlmClient([]))

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)

        result = runner.invoke(main, ["agent", "process", "999", "--yes"])
        assert result.exit_code != 0
        assert "not" in result.output.lower()


def test_process_nothing_proposed_reports_and_exits_zero() -> None:
    main, controller = _cli()
    _use_stub_llm(controller, StubLlmClient([_resp({"entities": []})]))

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        _add_person_schema(runner, main)

        Path("note.md").write_text("Nothing interesting here.\n")
        runner.invoke(main, ["doc", "ingest", "note.md"])

        result = runner.invoke(main, ["agent", "process", "1", "--yes"])
        assert result.exit_code == 0, result.output
        assert "Nothing to do" in result.output
        assert "total:" in result.output


def test_process_no_default_vault_errors() -> None:
    main, _controller = _cli()

    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["agent", "process", "1", "--yes"])
        assert result.exit_code != 0
        assert "No default vault is set" in result.output
        assert "forte vault create" in result.output


def test_process_unknown_vault_name_errors() -> None:
    main, _controller = _cli()

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)

        result = runner.invoke(main, ["agent", "process", "1", "--vault", "missing"])
        assert result.exit_code != 0
        assert "not registered" in result.output


def test_process_missing_api_key_errors(monkeypatch) -> None:
    """No stub client installed: the REAL `_build_llm_client` runs and must fail cleanly."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    main, _controller = _cli()

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)

        Path("note.md").write_text("Some text.\n")
        ingest = runner.invoke(main, ["doc", "ingest", "note.md"])
        assert ingest.exit_code == 0, ingest.output

        result = runner.invoke(main, ["agent", "process", "1", "--yes"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output
        assert "api" in result.output.lower() or "key" in result.output.lower()


# --- ingest ----------------------------------------------------------------------


def test_ingest_ingests_and_processes_in_one_command() -> None:
    main, controller = _cli()
    _use_stub_llm(controller, _stub_new_entity_with_field())

    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        _init_vault(runner, main)
        _add_person_schema(runner, main)

        Path("kickoff.md").write_text("Ada Lovelace wrote the first algorithm.\n")

        result = runner.invoke(main, ["agent", "ingest", "kickoff.md", "--yes"])
        assert result.exit_code == 0, result.output
        assert "Ingested doc #1: kickoff.md" in result.output

        listed = runner.invoke(main, ["entity", "list"])
        assert listed.exit_code == 0, listed.output
        assert "Ada Lovelace" in listed.output

        assert len(mentions_for_doc(Path(tmp), 1)) == 1


def test_ingest_no_default_vault_errors() -> None:
    main, _controller = _cli()

    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("kickoff.md").write_text("Hello.\n")

        result = runner.invoke(main, ["agent", "ingest", "kickoff.md", "--yes"])
        assert result.exit_code != 0
        assert "No default vault is set" in result.output


# --- review-flow routing precedence -----------------------------------------------


def test_process_default_is_bulk_editor() -> None:
    """With no flag, `agent process` uses the bulk editor by default."""
    main, controller = _cli()
    _use_stub_llm(controller, _stub_new_entity_with_field())
    editor = ScriptedEditor(_unchanged)
    _use_editor(controller, editor)

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        _add_person_schema(runner, main)

        Path("note.md").write_text("Ada Lovelace wrote the first algorithm.\n")
        runner.invoke(main, ["doc", "ingest", "note.md"])

        result = runner.invoke(main, ["agent", "process", "1"])
        assert result.exit_code == 0, result.output
        assert editor.calls == 1
        assert "## New entities" in editor.received

        listed = runner.invoke(main, ["entity", "list"])
        assert "Ada Lovelace" in listed.output


def test_process_interactive_flag_prompts_one_at_a_time() -> None:
    """`-i` selects the one-at-a-time [y/n] review; the editor is never opened."""
    main, controller = _cli()
    _use_stub_llm(controller, _stub_new_entity_with_field())
    editor = ScriptedEditor(_unchanged)
    _use_editor(controller, editor)

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        _add_person_schema(runner, main)

        Path("note.md").write_text("Ada Lovelace wrote the first algorithm.\n")
        runner.invoke(main, ["doc", "ingest", "note.md"])

        # Two prompts (entity proposal, then its field-set); approve both.
        result = runner.invoke(main, ["agent", "process", "1", "-i"], input="y\ny\n")
        assert result.exit_code == 0, result.output
        assert editor.calls == 0  # interactive path never opens the editor
        assert "Approve?" in result.output

        listed = runner.invoke(main, ["entity", "list"])
        assert "Ada Lovelace" in listed.output


def test_process_yes_wins_over_interactive_and_never_opens_editor() -> None:
    """--yes takes precedence over both the default bulk editor and --interactive:
    no editor, no prompts, everything auto-approved."""
    main, controller = _cli()
    _use_stub_llm(controller, _stub_new_entity_with_field())
    editor = ScriptedEditor(_unchanged)
    _use_editor(controller, editor)

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        _add_person_schema(runner, main)

        Path("note.md").write_text("Ada Lovelace wrote the first algorithm.\n")
        runner.invoke(main, ["doc", "ingest", "note.md"])

        # --yes alongside -i: --yes wins, no editor and no prompt input needed.
        result = runner.invoke(main, ["agent", "process", "1", "--yes", "-i"])
        assert result.exit_code == 0, result.output
        assert editor.calls == 0

        listed = runner.invoke(main, ["entity", "list"])
        assert "Ada Lovelace" in listed.output


def test_process_default_bulk_dry_run_writes_nothing() -> None:
    main, controller = _cli()
    _use_stub_llm(controller, _stub_new_entity_with_field())
    editor = ScriptedEditor(_unchanged)
    _use_editor(controller, editor)

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        _add_person_schema(runner, main)

        Path("note.md").write_text("Ada Lovelace wrote the first algorithm.\n")
        runner.invoke(main, ["doc", "ingest", "note.md"])

        result = runner.invoke(main, ["agent", "process", "1", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert editor.calls == 1  # editor still opens to collect decisions
        assert "Dry run" in result.output

        listed = runner.invoke(main, ["entity", "list"])
        assert "No entities yet." in listed.output


def test_process_default_bulk_editor_abort_exits_nonzero_and_commits_nothing() -> None:
    main, controller = _cli()
    _use_stub_llm(controller, _stub_new_entity_with_field())
    _use_editor(controller, ScriptedEditor(_abort_edit))

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        _add_person_schema(runner, main)

        Path("note.md").write_text("Ada Lovelace wrote the first algorithm.\n")
        runner.invoke(main, ["doc", "ingest", "note.md"])

        result = runner.invoke(main, ["agent", "process", "1"])
        assert result.exit_code != 0
        assert "user quit with :cq Nothing was committed." in result.output

        listed = runner.invoke(main, ["entity", "list"])
        assert "No entities yet." in listed.output


def test_process_structured_call_failure_reports_nothing_committed() -> None:
    """Malformed JSON on every retry surfaces the special-cased message."""
    main, controller = _cli()
    _use_stub_llm(controller, StubLlmClient(["not json"] * 10))

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        _add_person_schema(runner, main)

        Path("note.md").write_text("Ada Lovelace wrote the first algorithm.\n")
        runner.invoke(main, ["doc", "ingest", "note.md"])

        result = runner.invoke(main, ["agent", "process", "1", "--yes"])
        assert result.exit_code != 0
        assert "Agent run failed:" in result.output
        assert "Nothing was committed." in result.output

        listed = runner.invoke(main, ["entity", "list"])
        assert "No entities yet." in listed.output


def test_ingest_default_bulk_end_to_end() -> None:
    main, controller = _cli()
    _use_stub_llm(controller, _stub_new_entity_with_field())
    editor = ScriptedEditor(_unchanged)
    _use_editor(controller, editor)

    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_vault(runner, main)
        _add_person_schema(runner, main)

        Path("kickoff.md").write_text("Ada Lovelace wrote the first algorithm.\n")

        result = runner.invoke(main, ["agent", "ingest", "kickoff.md"])
        assert result.exit_code == 0, result.output
        assert "Ingested doc #1" in result.output
        assert editor.calls == 1

        listed = runner.invoke(main, ["entity", "list"])
        assert "Ada Lovelace" in listed.output


# --- vault selection ----------------------------------------------------------------


def test_process_targets_named_vault_and_leaves_default_untouched() -> None:
    main, controller = _cli()
    _use_stub_llm(controller, _stub_new_entity_with_field())

    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        _init_vault(runner, main)  # `test` is the default vault

        work = Path(tmp) / "work"
        work.mkdir()
        created = runner.invoke(main, ["vault", "create", "work", str(work)])
        assert created.exit_code == 0, created.output

        schema = runner.invoke(
            main,
            ["schema", "add", "person", "--field", "employer"]
            + ["--field", "role", "--vault", "work"],
        )
        assert schema.exit_code == 0, schema.output

        Path("note.md").write_text("Ada Lovelace wrote the first algorithm.\n")
        ingest = runner.invoke(main, ["doc", "ingest", "note.md", "--vault", "work"])
        assert ingest.exit_code == 0, ingest.output

        result = runner.invoke(main, ["agent", "process", "1", "--yes", "--vault", "work"])
        assert result.exit_code == 0, result.output

        in_work = runner.invoke(main, ["entity", "list", "--vault", "work"])
        assert "Ada Lovelace" in in_work.output

        in_default = runner.invoke(main, ["entity", "list"])
        assert "No entities yet." in in_default.output


def test_ingest_into_named_vault() -> None:
    main, controller = _cli()
    _use_stub_llm(controller, _stub_new_entity_with_field())

    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        _init_vault(runner, main)

        work = Path(tmp) / "work"
        work.mkdir()
        runner.invoke(main, ["vault", "create", "work", str(work)])
        runner.invoke(
            main,
            ["schema", "add", "person", "--field", "employer"]
            + ["--field", "role", "--vault", "work"],
        )

        Path("kickoff.md").write_text("Ada Lovelace wrote the first algorithm.\n")

        result = runner.invoke(main, ["agent", "ingest", "kickoff.md", "--yes", "--vault", "work"])
        assert result.exit_code == 0, result.output

        in_work = runner.invoke(main, ["doc", "list", "--vault", "work"])
        assert "kickoff.md" in in_work.output

        in_default = runner.invoke(main, ["doc", "list"])
        assert "No documents yet." in in_default.output


# --- help ---------------------------------------------------------------------------


def test_help_renders_flags_and_vault_option() -> None:
    main, _controller = _cli()
    runner = CliRunner()

    group_help = runner.invoke(main, ["agent", "--help"])
    assert group_help.exit_code == 0, group_help.output
    assert "process" in group_help.output
    assert "ingest" in group_help.output

    for subcommand in ("process", "ingest"):
        out = runner.invoke(main, ["agent", subcommand, "--help"])
        assert out.exit_code == 0, out.output
        assert "--yes" in out.output
        assert "--dry-run" in out.output
        assert "--interactive" in out.output
        assert "--vault" in out.output
        # Click wraps help text, so compare against a whitespace-normalized copy.
        assert "Takes precedence over --interactive." in " ".join(out.output.split())

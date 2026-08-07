# docs/impl/2026-08-06/agent-migration-tasks.md

Feature: migrate the last unmigrated command group — `forte agent` — into the 3-layer structure
(`controller` / `service` / `interface` / `client` / `model`), then delete the legacy
`services/`, `db/`, `domain/`, and `cli/` packages and switch the installed entrypoint to
`forte.main`. This completes the refactor started in `docs/impl/2026-08-05/service-refactor-tasks.md`
and the vault work in `docs/impl/2026-08-06/vault-management-tasks.md`.

- Migrate per-vault config into the new stack (fixes a live `forte.yaml` path bug)
- Move the LLM boundary into `interface/` + `client/`
- Port the agent pipeline into `service/` as `AgentService`
- Move the reviewer and editor seams into the controller layer
- Add `CliAgentController` with `--vault`
- Switch the entrypoint to `forte.main` and delete the legacy packages
- Update the agent specs for the new vault model

---

Task: Migrate per-vault config into the new stack (fixes a live `forte.yaml` path bug)
ACs:
- A `ConfigService` in `service/config_service.py` exposes the vault's resolved config (extraction model, Anthropic API key, editor), constructor-injected with an `IConfigStore` interface (`interface/config_store.py`) implemented by a `YamlConfigStore` in `client/`.
- The config is read from the CURRENT vault layout — `<vault_root>/forte.yaml` via `model/vault.py`'s `VaultLayout.config_path` — resolved through the injected `VaultContext`, exactly like the SQLite clients do.
- Reader tolerance is preserved from `services/config.py`: a missing file or missing keys fall back to documented defaults (`extraction_model` → `claude-haiku-4-5`, api key and editor → `None`) rather than raising. `${VAR}` interpolation against the process environment is preserved.
- `ConfigError` / `MissingAPIKeyError` move to `model/config.py` per the style guide, with `require_api_key`-equivalent behavior available to callers that actually need a key.
- `Config` becomes a model dataclass in `model/config.py`.
- Unit tests cover: missing file, empty file, partial keys, `${VAR}` set and unset, literal key values, and `require_api_key` raising when no key resolves.
Implementation Notes:
- THIS TASK FIXES A REAL BUG, not just a file move. `services/config.py`'s `load_config(root)` computes its path as `VaultLayout(root).config_path` using the LEGACY `domain/vault.py`, which still points at `.forte/config.yaml`. Vaults created by the new `forte vault create` write `forte.yaml` at the vault root instead. Because the reader is deliberately tolerant, it does not error — it silently returns defaults, so on a new vault the agent would lose the configured model and the API key would read as unset. Add a regression test that a `forte.yaml` written by `forte vault create` is actually read back.
- Do not delete legacy `services/config.py` yet — legacy `cli/` and `cli/bulk_editor.py` still import it, and the cleanup task removes it. Just make sure nothing in `service/`, `client/`, `controller/` imports the legacy one.
- `LocalVaultFs.write_default_config(path)` already takes an explicit path and is correct; leave it alone. Only the READER had the bug.

Task: Move the LLM boundary into `interface/` + `client/`
ACs:
- `interface/llm_client.py` defines `ILlmClient` (ABC, per style guide — the current `LLMClient` is a `typing.Protocol` in `services/agent/_llm.py`) with the single `messages(*, system, user, schema) -> LlmResponse` operation.
- `client/anthropic_llm_client.py` implements it, carrying over `AnthropicLLMClient`'s model/api_key/max_tokens construction and its request/response translation unchanged.
- `LlmResponse` moves to `model/agent.py` (or a dedicated `model/llm.py` — use judgement, note the choice) since both the service and the client depend on it.
- The `StubLLMClient` test double moves somewhere tests can still reach it (e.g. `tests/` or a fake in the test module) — it must NOT ship in `client/` as production code.
- The whole test suite stays deterministic and never makes a real network call.
Implementation Notes:
- Per the style guide, interfaces are named `I<Noun>` and clients are `<technology><Interface>`, so `ILlmClient` → `AnthropicLlmClient`. Keep method bodies as thin translation with no business logic.
- `_structured.py`'s retry/validation logic around structured calls is business logic, NOT client logic — it stays in the service layer with the pipeline (next task), not in the client.
- Can be done in parallel with the config task.

Task: Port the agent pipeline into `service/` as `AgentService`
ACs:
- `service/agent_service.py` defines `AgentService` as a class with its dependencies constructor-injected: `ILlmClient`, `ConfigService`, and the existing `DocumentService`, `EntityService`, `SchemaService` (or the narrower interfaces they sit on — use judgement, but the service must NOT import from `services/`, `db/`, or `domain/`).
- `AgentService` exposes the two operations the CLI needs, replacing `process_document` / `process_document_bulk`: a per-proposal-review path taking an injected reviewer, and a bulk single-editor-pass path taking an injected editor session. Both accept `dry_run`.
- The pipeline internals currently in `services/agent/` (`_orchestrator`, `_steps`, `_prompts`, `_structured`, `_commit`, `_bulk_format`, `_usage`, `_cost`, `_pipeline_models`) move under `service/agent/` (a private sub-package is fine — the style guide's one-file-per-service rule shouldn't force a 1,500-line module). They keep their leading-underscore privacy: only `AgentService` is imported from outside.
- All legacy dependencies are replaced by injected ones. Specifically: `_orchestrator`'s `get_document` / `list_schemas` / `EntityRepository(root).list()` / `from_markdown`, `_commit`'s `services.document` + `services.entity` module calls, and `_steps`' `find_candidates` import.
- `find_candidates` (`services/linking.py`) moves into the new stack alongside the entity service as a pure function, per the earlier refactor plan.
- Document markdown parsing (`domain/document_markdown.py`'s `from_markdown`) is available to the new stack — move it to `model/` or wherever the document refactor put its markdown handling, without duplicating it.
- No `root: Path` threading: the pipeline reaches storage through the injected services, which resolve the vault via `VaultContext` as everything else now does.
- `ProposedChange` / `ProposedLink` / `ProposedNewEntity` / `ProposedFieldSet` / `Decision` / `ProcessResult` move to `model/agent.py`; `StructuredCallError` and any other agent exceptions get an `AgentError` base class there per the style guide.
- All existing agent behavior is preserved: the routing precedence (`yes` beats `interactive`, default is the bulk editor pass), `dry_run` composing with all three paths, best-effort commit with a success/failure report, and usage/cost accumulation.
- The existing agent test suites (`tests/test_agent.py`, `test_agent_bulk.py`, `test_steps.py`, `test_commit.py`, `test_prompts.py`, `test_structured.py`, `test_orchestrator`-adjacent, `test_bulk_format.py`, `test_cost.py`, `test_review.py`, `test_llm.py`, `test_pipeline_models.py`) are ported and pass against the new structure.
Implementation Notes:
- THIS IS THE BIG ONE — roughly 1,700 lines across the pipeline plus its tests, and it's where the whole migration's risk sits. Do it in one focused pass, and lean on the existing tests as the safety net: they encode behavior that is NOT written down anywhere else.
- `_commit.py`'s docstring says it deliberately goes "through the EXISTING service layer" rather than touching repositories — that intent carries over cleanly; it now goes through the injected `DocumentService`/`EntityService` instead. `entity.add_entity` → `EntityService.add_entity`, `document.link_document` → `DocumentService.link_document`, `entity.get_entity`/`edit_entity` → the `EntityService` equivalents. Check the signatures — the new services take no `root` and use keyword args in places the old module functions didn't.
- Reviewer and editor stay as injected seams (`Reviewer` / `EditorSession`). Their PROTOCOLS can stay with the service (they're service-layer dependencies); their concrete terminal implementations belong to the controller layer — see the next task.
- Depends on the config and LLM tasks.

Task: Move the reviewer and editor seams into the controller layer
ACs:
- `InteractiveReviewer` (currently `cli/review_tui.py`) and `TerminalEditorSession` + `resolve_editor_command` (currently `cli/bulk_editor.py`) live in the new stack under `controller/` (e.g. `controller/interactive_reviewer.py`, `controller/terminal_editor.py`), since both are pure terminal-interaction concerns.
- They satisfy the `Reviewer` / `EditorSession` seams that `AgentService` depends on, and import the proposal models from `model/agent.py` rather than from the agent package's privates.
- `resolve_editor_command`'s precedence is preserved exactly: `$VISUAL` → `$EDITOR` → the config's `editor:` key → fallback. It reads config through the new `ConfigService`, not legacy `services/config.py`.
- `EditorAbortedError` moves to `model/agent.py` with the other agent errors.
- `tests/test_review_tui.py` and `tests/test_bulk_editor.py` are ported and pass.
Implementation Notes:
- The style guide has no explicit slot for "a non-Click interactive component", but these are unambiguously user-interface code, and controllers are where user interaction lives — hence `controller/`. They are not Click groups, so they don't get a `group()` method; they're plain classes the `CliAgentController` constructs. Note this in their class docstrings so the next reader doesn't think they're misfiled.
- Depends on `AgentService` defining the seams.

Task: Add `CliAgentController` with `--vault`
ACs:
- `controller/cli_agent_controller.py` defines `CliAgentController`, constructor-injected with `AgentService` (plus whatever it needs to build the reviewer/editor), exposing a `group()` method that builds the `agent` Click group following `CliVaultController`/`CliSchemaController`'s shape exactly.
- Commands `forte agent process <doc_id>` and `forte agent ingest <path>` preserve their current flags and help text: `--yes`/`-y`, `--dry-run`, `--interactive`/`-i`, including the documented precedence that `--yes` beats `--interactive`.
- Both accept `--vault <name>` in the same position and with the same behavior as `schema`/`entity`/`doc` (per-subcommand, resolving through `VaultService.resolve_vault` and setting the `VaultContext` — match exactly what `cli_document_controller.py` does now).
- `agent ingest` still ingests via the document service first, echoes `Ingested doc #N: <name>`, then runs the pipeline against the new doc id.
- The result rendering currently in `_render_process_result` and the cost summary (`format_cost_summary`) move into the controller — this is presentation, not business logic. Output text is unchanged.
- Error mapping follows the style guide: catch the feature base error (`AgentError`) together with `DocumentError` and `VaultError`, re-raised as `click.ClickException`. Preserve the two special-cased messages: a structured-call failure renders as `Agent run failed: {e}. Nothing was committed.` and an editor abort as `{e} Nothing was committed.`
- The construction seams that tests monkeypatch (`_build_llm_client`, `_build_editor_session`) survive in some form so the suite stays deterministic and free — as controller methods or as `main.py` wiring the tests can override. Note which you chose.
- Wired into `main.py`. `tests/test_agent_cli.py` is ported and passes.
Implementation Notes:
- Depends on `AgentService` and the reviewer/editor task.
- The `_run_agent_process` routing helper in `cli/__init__.py` has a long docstring explaining the three-way routing precedence — carry that reasoning across; it's the clearest statement of the intended behavior anywhere in the codebase.

Task: Switch the entrypoint to `forte.main` and delete the legacy packages
ACs:
- `pyproject.toml`'s `[project.scripts]` points `forte` at `forte.main:main`.
- `src/forte/services/`, `src/forte/db/`, `src/forte/domain/`, and `src/forte/cli/` are deleted in full.
- `grep -rn "from forte.services\|from forte.db\|from forte.domain\|from forte.cli" src/ tests/` returns nothing.
- Every command available before the migration is available after it: `schema` (add/list/remove), `entity` (add/list/show/edit/remove), `doc` (ingest/list/show/link/unlink/remove), `agent` (process/ingest), `vault` (create/list/show/remove/set-default). `forte init` is intentionally gone, replaced by `forte vault create`.
- Legacy-only test files that tested deleted modules are removed (`tests/test_doc_cli.py`, `tests/test_schema_cli.py`, `tests/test_entity_cli.py`, `tests/test_discovery.py`, `tests/test_forte_init.py`, `tests/test_vault_layout.py`, the `db/` repository tests, `tests/test_config_writer.py`/`test_config_service.py` as applicable) — but ONLY where an equivalent new-stack test already covers the behavior. Do not delete a test that is the only coverage of a behavior; port it instead, and list anything you deleted without a replacement.
- `tests/smoketest.sh` and `tests/smoketest-agent.sh` are updated for `forte vault create` and `--vault`, and pass.
- Full suite passes with no failures at all.
Implementation Notes:
- NOTE ON THE BASELINE: three tests in `tests/test_doc_cli.py` (`test_show_displays_linked_entities`, `test_link_happy_path`, `test_link_twice_is_idempotent`) have been failing throughout this refactor. They test the LEGACY CLI. This task deletes that file, which makes them disappear rather than fixing them — before deleting, confirm the equivalent new-stack behavior (doc↔entity linking showing up in `doc show`) IS covered by `tests/test_cli_document_controller.py`, and if it isn't, port a test for it. Do not let a real linking bug get swept away with the legacy code.
- Do this LAST. Grep before each deletion, not after.
- Flipping the entrypoint is the step that actually ships all of this to an installed `forte` binary — until then everything runs only via `python -m forte.main`.

Task: Update the agent specs for the new vault model
ACs:
- `docs/spec/forte-agent.md` and `docs/spec/forte-agent-bulk-commit.md` are consistent with the migrated behavior: vault resolution via default/`--vault` rather than cwd discovery, and `forte.yaml` rather than `.forte/config.yaml` for model and API-key settings.
- Scenarios exist for `forte agent process --vault <name>` and for running with no default vault set, matching the patterns the other spec files now use.
- `docs/solution-design.md`'s CLI command table includes `agent` with `--vault`, and any remaining `.forte/` references anywhere in `docs/` are gone (`grep -rn "\.forte/" docs/` should only match the user-level `~/.forte/` registry).
Implementation Notes:
- Small task, mostly consistency sweeps. The earlier vault work already updated the "Given a default vault is set" preconditions in these files — verify rather than redo, and focus on the config-path and agent-specific bits that migration touched.
- Can run in parallel with the code tasks; it depends on decisions, not on code.

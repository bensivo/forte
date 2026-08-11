from pathlib import Path

import click

from forte.client.anthropic_llm_client import AnthropicLlmClient
from forte.controller.interactive_reviewer import InteractiveReviewer
from forte.interface.editor import IEditor
from forte.interface.llm_client import ILlmClient
from forte.model.agent import (
    AgentError,
    EditorAbortedError,
    ProcessResult,
    StructuredCallError,
)
from forte.model.config import ConfigError
from forte.model.document import DocumentError
from forte.model.vault import VaultContext, VaultError
from forte.service.agent_service import AgentService, AutoApproveReviewer
from forte.service.config_service import ConfigService
from forte.service.document_service import DocumentService
from forte.service.vault_service import VaultService


# Adds the shared `--vault <name>` selector to an agent subcommand. Defined
# once so every subcommand spells the option identically.
def _vault_option(f):
    return click.option(
        "--vault",
        "vault_name",
        default=None,
        help="Name of the vault to operate on (defaults to the default vault).",
    )(f)


# Help text for `--interactive`/`-i`, shared by `process` and `ingest`.
_INTERACTIVE_HELP = (
    "Review proposals one at a time with a [y/n] prompt for each, instead of "
    "the default single text-editor pass. Ignored if --yes is also given -- "
    "--yes takes precedence, auto-approving everything with no prompts."
)

# Help text for `--yes`/`-y`, shared by `process` and `ingest`.
_YES_HELP = "Auto-approve all proposed changes. Takes precedence over --interactive."


class CliAgentController:
    """
    CLI interface for AgentService. Wires the LLM pipeline up as an `agent`
    Click command group (process/ingest), translating AgentError,
    DocumentError, ConfigError, and VaultError into Click errors. Contains no
    business logic of its own, but does own two presentation concerns that are
    not the service's job: rendering a run's result, and choosing WHICH review
    flow a given combination of flags selects.

    Vault selection: `--vault <name>` is a per-subcommand option, so it is
    written after the subcommand (`forte agent process 7 --vault work`). The
    same placement is used by the `schema`, `entity`, and `doc` groups. Each
    subcommand resolves the named vault (or the default vault when the option
    is omitted) and points the shared VaultContext at it BEFORE anything else
    happens, so no config is read and no LLM client is built (let alone
    called) when the vault cannot be resolved.

    Construction seams: the real LLM client is built by `_build_llm_client`,
    lazily, per invocation -- a method so tests can monkeypatch it on the
    controller instance and keep the suite deterministic and free of API
    keys. The LLM client is built up front (before the service is called)
    rather than behind a lazy proxy so that a missing API key fails fast with
    a clean message instead of surfacing from inside a retry loop, and it is
    installed on the injected AgentService — whose `llm_client` is read per
    call — right before the run. The `IEditor` used by the bulk flow is NOT
    built here: it is a single instance constructed once in `main.py` and
    injected into this controller, since it has no wiring-time vault or
    config dependency to resolve lazily.
    """

    def __init__(
        self,
        agent_service: AgentService,
        document_service: DocumentService,
        config_service: ConfigService,
        vault_service: VaultService,
        vault_context: VaultContext,
        editor: IEditor,
    ):
        """
        Args:
            agent_service (AgentService): The service to call for all agent
                pipeline runs.
            document_service (DocumentService): Used by `agent ingest` to
                ingest the file before the pipeline runs against it.
            config_service (ConfigService): Supplies the extraction model and
                API key the LLM client is built from.
            vault_service (VaultService): The service used to resolve which
                vault a subcommand operates on.
            vault_context (VaultContext): The shared context the resolved
                vault root is written to before each service call.
            editor (IEditor): The single-pass review seam for the default
                bulk flow.
        """
        self.agent_service = agent_service
        self.document_service = document_service
        self.config_service = config_service
        self.vault_service = vault_service
        self.vault_context = vault_context
        self.editor = editor

    def group(self) -> click.Group:
        """
        Build the `agent` Click command group.

        Returns:
            (click.Group) The `agent` command group, ready to attach to a
                parent Click group.
        """
        controller = self

        @click.group()
        def agent() -> None:
            """Run the LLM agent pipeline over documents."""

        @agent.command("process")
        @click.argument("doc_id", type=int)
        @click.option("--yes", "-y", is_flag=True, help=_YES_HELP)
        @click.option("--dry-run", is_flag=True, help="Propose changes but write nothing.")
        @click.option("--interactive", "-i", is_flag=True, help=_INTERACTIVE_HELP)
        @_vault_option
        def agent_process(
            doc_id: int, yes: bool, dry_run: bool, interactive: bool, vault_name: str | None
        ) -> None:
            """Run the extract/link/field-extract pipeline against document DOC_ID."""
            controller._process(doc_id, yes, dry_run, interactive, vault_name)

        @agent.command("ingest")
        @click.argument("path", type=click.Path(exists=False))
        @click.option("--yes", "-y", is_flag=True, help=_YES_HELP)
        @click.option("--dry-run", is_flag=True, help="Propose changes but write nothing.")
        @click.option("--interactive", "-i", is_flag=True, help=_INTERACTIVE_HELP)
        @_vault_option
        def agent_ingest(
            path: str, yes: bool, dry_run: bool, interactive: bool, vault_name: str | None
        ) -> None:
            """Ingest the file at PATH, then run the agent pipeline against it."""
            controller._ingest(path, yes, dry_run, interactive, vault_name)

        return agent

    def _select_vault(self, vault_name: str | None) -> None:
        """
        Point the shared VaultContext at the vault this invocation targets.

        Args:
            vault_name (str | None): An explicit vault name from `--vault`, or
                None to use the default vault.

        Returns:
            None

        Raises:
            VaultError: if the named vault is not registered, or no name was
                given and no default vault is set.
        """
        vault = self.vault_service.resolve_vault(vault_name)
        self.vault_context.set_root(vault.path)

    def _build_llm_client(self) -> ILlmClient:
        """
        Construct the real LLM client from the active vault's config.

        This is a construction seam: tests monkeypatch it to return a stub
        client so the whole test suite stays deterministic and free.
        Production code always gets a real AnthropicLlmClient here.

        Returns:
            (ILlmClient) The LLM boundary every pipeline step will call.

        Raises:
            MissingAPIKeyError: if no Anthropic API key is configured.
            NoDefaultVaultError: if no vault is selected.
        """
        config = self.config_service.get_config()
        return AnthropicLlmClient(
            model=config.extraction_model,
            api_key=self.config_service.require_api_key(),
        )

    def _process(
        self,
        doc_id: int,
        yes: bool,
        dry_run: bool,
        interactive: bool,
        vault_name: str | None,
    ) -> None:
        try:
            self._select_vault(vault_name)
        except VaultError as e:
            raise click.ClickException(str(e))

        self._run(doc_id, yes=yes, dry_run=dry_run, interactive=interactive)

    def _ingest(
        self,
        path: str,
        yes: bool,
        dry_run: bool,
        interactive: bool,
        vault_name: str | None,
    ) -> None:
        try:
            self._select_vault(vault_name)
            document = self.document_service.ingest_document(Path(path))
        except (DocumentError, VaultError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Ingested doc #{document.id}: {document.name}")

        self._run(document.id, yes=yes, dry_run=dry_run, interactive=interactive)

    def _run(self, doc_id: int, *, yes: bool, dry_run: bool, interactive: bool) -> None:
        """
        Shared process-and-render logic for `agent process` and `agent ingest`.

        Routing precedence -- kept in this ONE place so both commands behave
        identically. It is a CONTROLLER decision, not a service one: the
        service exposes two flows, and the flags pick between them.

          - `yes` -> the auto-approve path (`process_document` with
            `AutoApproveReviewer`): no prompts, no editor, everything
            approved. `yes` wins over `interactive` (documented on both
            flags' `--help`).
          - `interactive` (without `yes`) -> the one-at-a-time review flow
            (`process_document` with `InteractiveReviewer`), prompting per
            proposal.
          - neither -> the DEFAULT bulk flow: review every proposal in a
            single text-editor pass (`process_document_bulk`), using the
            `IEditor` injected into this controller.

        `dry_run` composes with all three: nothing is committed, but
        proposals are still gathered.

        Args:
            doc_id (int): The id of the already-ingested document to process.
            yes (bool): Auto-approve every proposal.
            dry_run (bool): Run the full flow but write nothing.
            interactive (bool): Review one proposal at a time. Ignored when
                `yes` is set.

        Returns:
            None

        Raises:
            click.ClickException: if the config, the pipeline, or the commit
                step fails. Nothing is committed in any of those cases.
        """
        try:
            self.agent_service.llm_client = self._build_llm_client()
        except (ConfigError, VaultError) as e:
            raise click.ClickException(str(e))

        try:
            if yes:
                result = self.agent_service.process_document(
                    doc_id, reviewer=AutoApproveReviewer(), dry_run=dry_run
                )
            elif interactive:
                result = self.agent_service.process_document(
                    doc_id, reviewer=InteractiveReviewer(), dry_run=dry_run
                )
            else:
                result = self.agent_service.process_document_bulk(
                    doc_id, editor=self.editor, dry_run=dry_run
                )
        except StructuredCallError as e:
            raise click.ClickException(f"Agent run failed: {e}. Nothing was committed.")
        except EditorAbortedError as e:
            raise click.ClickException(f"{e} Nothing was committed.")
        except (AgentError, DocumentError, ConfigError, VaultError) as e:
            raise click.ClickException(str(e))

        self._render_process_result(result)

    def _render_process_result(self, result: ProcessResult) -> None:
        """
        Print a finished run's outcome, followed by its cost summary.

        Args:
            result (ProcessResult): The outcome of the run to render.

        Returns:
            None

        Raises:
            click.ClickException: if the cost summary cannot be priced
                because no vault is selected.
        """
        if not result.approved_changes:
            click.echo("Nothing to do: no proposals were generated for this document.")
            click.echo(self._cost_summary(result))
            return

        if result.dry_run:
            click.echo(f"Dry run: {len(result.approved_changes)} change(s) would be committed:")
            for change in result.approved_changes:
                click.echo(f"  - {change}")
            click.echo("Nothing was written.")
        else:
            report = result.commit_report
            assert report is not None
            click.echo(
                f"Committed {len(report.successes)} change(s), "
                f"{len(report.failures)} failure(s)."
            )
            for failure in report.failures:
                click.echo(f"  FAILED: {failure.change} -- {failure.error}")

        click.echo(self._cost_summary(result))

    def _cost_summary(self, result: ProcessResult) -> str:
        try:
            return self.agent_service.format_cost_summary(result.usage)
        except VaultError as e:
            raise click.ClickException(str(e))

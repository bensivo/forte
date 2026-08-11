"""The agent feature's service layer: LLM-driven extract/link/field/commit.

`AgentService` is the only thing outside `service/agent/` that anyone imports
from the agent pipeline. The pipeline's internals (prompts, structured-call
retries, the three LLM steps, the two orchestrators, the bulk editor document
format, the best-effort committer, and cost reporting) live in the private
`forte.service.agent` sub-package.

The reviewer seam is re-exported here (`Reviewer`, `AutoApproveReviewer`,
`ScriptedReviewer`) because it is part of this service's call signature —
callers must be able to pass one in. Its concrete interactive implementation
belongs to the controller layer. The editor seam is `forte.interface.editor.
IEditor`, a feature-neutral interface that lives in `interface/` rather than
being re-exported from here, since it is not specific to the agent feature.
"""

from __future__ import annotations

from forte.interface.editor import IEditor
from forte.interface.llm_client import ILlmClient
from forte.model.agent import ProcessResult
from forte.model.llm import Usage
from forte.service.agent._cost import format_cost_summary
from forte.service.agent._orchestrator import process_document, process_document_bulk
from forte.service.agent._review import AutoApproveReviewer, Reviewer, ScriptedReviewer
from forte.service.config_service import ConfigService
from forte.service.document_service import DocumentService
from forte.service.entity_service import EntityService
from forte.service.schema_service import SchemaService

__all__ = [
    "AgentService",
    "AutoApproveReviewer",
    "Reviewer",
    "ScriptedReviewer",
]


class AgentService:
    """
    Contains the two operations the agent feature exposes over an
    already-ingested document, which differ ONLY in how proposed changes are
    reviewed:

    - `process_document`: the "option B" flow. Review happens BETWEEN steps
      (entity proposals first, then field-sets), so a rejected entity never
      pays for a field-extraction call. Takes an injected `Reviewer`.
    - `process_document_bulk`: the DEFAULT flow. Every proposal is reviewed in
      a SINGLE editor pass, which means every proposed entity must be
      field-extracted up front. Takes an injected `IEditor`.

    Both accept `dry_run`, which composes with either path: the full flow
    (including review) still runs, but the commit step is skipped entirely and
    nothing is written.

    All storage access goes through the injected document / entity / schema
    services, which resolve the active vault themselves — there is no vault
    root threaded through this service or the pipeline beneath it.
    """

    def __init__(
        self,
        llm_client: ILlmClient,
        config_service: ConfigService,
        document_service: DocumentService,
        entity_service: EntityService,
        schema_service: SchemaService,
    ):
        """
        Args:
            llm_client (ILlmClient): The LLM boundary every pipeline step calls.
            config_service (ConfigService): Resolves the vault's configuration,
                used for the extraction model a cost summary is priced against.
            document_service (DocumentService): Reads document text and records
                doc-entity links at commit time.
            entity_service (EntityService): Supplies existing entities for link
                resolution, and creates/edits entities at commit time.
            schema_service (SchemaService): Supplies the vault's schemas and
                their declared field names.
        """
        self.llm_client = llm_client
        self.config_service = config_service
        self.document_service = document_service
        self.entity_service = entity_service
        self.schema_service = schema_service

    def process_document(
        self, doc_id: int, *, reviewer: Reviewer, dry_run: bool = False
    ) -> ProcessResult:
        """
        Process a document, reviewing proposals one batch at a time.

        Runs extract -> review entities -> link/create -> field-extract the
        survivors -> review field-sets -> commit. Only approved entity
        proposals are field-extracted.

        Args:
            doc_id (int): The id of the already-ingested document to process.
            reviewer (Reviewer): The approval seam consulted at each review
                point. `AutoApproveReviewer` backs the `--yes` flag.
            dry_run (bool): When True, run the full flow but write nothing.

        Returns:
            (ProcessResult) The approved changes, the commit report (None on a
                dry run), and the run's accumulated token usage.

        Raises:
            DocumentNotFoundError: if ``doc_id`` does not exist.
            StructuredCallError: if a pipeline step exhausts its retries. The
                run aborts with nothing committed, since commit runs last.
            NoDefaultVaultError: if no vault is selected (propagated from the
                injected services' storage clients).
        """
        return process_document(
            doc_id,
            llm=self.llm_client,
            reviewer=reviewer,
            document_service=self.document_service,
            entity_service=self.entity_service,
            schema_service=self.schema_service,
            dry_run=dry_run,
        )

    def process_document_bulk(
        self, doc_id: int, *, editor: IEditor, dry_run: bool = False
    ) -> ProcessResult:
        """
        Process a document, reviewing every proposal in one editor pass.

        Because there is no earlier review point to prune the proposal set,
        EVERY proposed entity is field-extracted before the editor opens —
        strictly more LLM calls than `process_document`, and the intrinsic
        cost of showing the user everything at once. When nothing at all is
        proposed the editor is not opened.

        Args:
            doc_id (int): The id of the already-ingested document to process.
            editor (IEditor): The single-pass review seam.
            dry_run (bool): When True, run the full flow (the editor still
                opens) but write nothing.

        Returns:
            (ProcessResult) The approved changes, the commit report (None on a
                dry run), and the run's accumulated token usage.

        Raises:
            DocumentNotFoundError: if ``doc_id`` does not exist.
            StructuredCallError: if a pipeline step exhausts its retries.
            EditorAbortedError: if the editor exits non-zero.
            NoDefaultVaultError: if no vault is selected (propagated from the
                injected services' storage clients).
        """
        return process_document_bulk(
            doc_id,
            llm=self.llm_client,
            editor=editor,
            document_service=self.document_service,
            entity_service=self.entity_service,
            schema_service=self.schema_service,
            dry_run=dry_run,
        )

    def format_cost_summary(self, usage: Usage) -> str:
        """
        Summarize a run's token usage and estimated USD cost.

        Prices ``usage`` against the vault's configured extraction model —
        the same model the run's LLM calls were made with. An unknown model
        degrades gracefully to a token-only summary.

        Args:
            usage (Usage): The token usage accumulated over a run.

        Returns:
            (str) A one-line token + estimated-cost summary.

        Raises:
            NoDefaultVaultError: if no vault is selected (propagated from the
                injected ConfigService).
        """
        model = self.config_service.get_config().extraction_model
        return format_cost_summary(model, usage)

"""The pipeline orchestrator: the stepwise state machine tying the agent together.

``process_document`` drives the full "option B" flow for one already-ingested
document:

    extract -> review entities -> link/create -> (implicit) -> field-extract
    survivors -> review field-sets -> commit

"Option B" means review happens BETWEEN steps, so the expensive per-entity
field-extraction call NEVER runs on a rejected entity proposal — only approved
entity proposals are field-extracted. All state is held IN MEMORY: there is no
``ingest_changes`` table, no persistence, and no resume. If the run is
interrupted, in-flight progress is lost with nothing committed (commit happens
once, at the very end).

Presentation decoupling: this module has NO Click and NO Rich imports. It takes
an :class:`~forte.services.llm.LLMClient` and a
:class:`~forte.services.review.Reviewer` (both injected) plus the vault root,
and returns a plain :class:`ProcessResult` that the CLI renders.

Failure semantics: if any pipeline step exhausts its retries it raises
:class:`~forte.services.structured.StructuredCallError`, which propagates out of
``process_document`` uncaught. Because commit is the last thing that runs,
nothing has been written when a step fails — the run aborts with an empty vault
delta.

Ordering: approved entity proposals are presented and committed
new-entities-first, then links. This is also how ``approved_changes`` is
constructed (new entities, then links, then field-sets), which keeps each
:class:`~forte.services.pipeline_models.FieldSetTarget.new_entity_ref` aligned
with :func:`~forte.services.commit.commit_changes`' resolution scheme: commit
keys ``new_entity_ref`` by a new entity's position among the
``ProposedNewEntity`` items in the changes list, and we assign each
``new_entity_ref`` as that entity's index within the approved-new-entities list
passed in that same order.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from forte.db.entity_repository import EntityRepository
from forte.domain.document_markdown import from_markdown
from forte.services.commit import CommitReport, commit_changes
from forte.services.document import get_document
from forte.services.llm import LLMClient
from forte.services.pipeline_models import (
    FieldSetTarget,
    ProposedChange,
    ProposedLink,
    ProposedNewEntity,
)
from forte.services.review import Reviewer
from forte.services.schema import list_schemas
from forte.services.steps import extract_entities, extract_fields, resolve_candidate
from forte.services.usage import Usage


@dataclass
class ProcessResult:
    """The outcome of one ``process_document`` run.

    ``commit_report`` is ``None`` on a dry run (commit skipped entirely);
    otherwise it is the best-effort :class:`CommitReport` for the committed
    ``approved_changes``. ``usage`` is the token usage accumulated across every
    LLM call the run made.
    """

    doc_id: int
    approved_changes: list[ProposedChange]
    commit_report: CommitReport | None
    usage: Usage
    dry_run: bool


def _read_doc_text(root: Path, doc_id: int) -> str:
    """Load the processed-body text for ``doc_id`` the same way ``doc show`` does."""
    document = get_document(root, doc_id)  # propagates DocumentNotFoundError
    if not document.processed_path:
        return ""
    processed_text = (root / document.processed_path).read_text()
    return from_markdown(processed_text).body


def process_document(
    root: Path,
    doc_id: int,
    *,
    llm: LLMClient,
    reviewer: Reviewer,
    dry_run: bool = False,
) -> ProcessResult:
    """Run the extract -> review -> link -> review -> field -> review -> commit flow.

    See the module docstring for the full "option B" contract. Raises
    :class:`~forte.services.document.DocumentNotFoundError` if ``doc_id`` does
    not exist, and lets :class:`~forte.services.structured.StructuredCallError`
    propagate (aborting the run with nothing committed) if any step exhausts its
    retries.
    """
    doc_text = _read_doc_text(root, doc_id)

    schemas = list_schemas(root)
    schema_names = [s.name for s in schemas]
    schema_field_names = {s.name: list(s.fields) for s in schemas}
    existing_entities = EntityRepository(root).list()

    usage = Usage.zero()

    # 1. Extract candidate entities.
    candidates, u = extract_entities(llm, doc_text=doc_text, schema_names=schema_names)
    usage += u

    # 2. Resolve each candidate to a link or a new-entity proposal.
    entity_proposals: list[ProposedLink | ProposedNewEntity] = []
    for candidate in candidates:
        proposal, u = resolve_candidate(
            llm,
            candidate=candidate,
            doc_text=doc_text,
            existing_entities=existing_entities,
        )
        usage += u
        entity_proposals.append(proposal)

    # 3. Review entity proposals: new entities first, then links.
    new_proposals = [p for p in entity_proposals if isinstance(p, ProposedNewEntity)]
    link_proposals = [p for p in entity_proposals if isinstance(p, ProposedLink)]
    ordered_entity_proposals: list[ProposedChange] = [*new_proposals, *link_proposals]

    approved_entities = [
        d.change for d in reviewer.review(ordered_entity_proposals) if d.approved
    ]
    approved_new = [c for c in approved_entities if isinstance(c, ProposedNewEntity)]
    approved_links = [c for c in approved_entities if isinstance(c, ProposedLink)]

    # 4. Field-extract ONLY approved entity proposals (the option-B cost win).
    #    New entities keep the same order here as in approved_changes below, so
    #    their new_entity_ref (index within approved_new) matches commit's keys.
    field_proposals: list[ProposedChange] = []
    for index, new_entity in enumerate(approved_new):
        target = FieldSetTarget(
            name=new_entity.name, schema=new_entity.schema, new_entity_ref=index
        )
        field_set, u = extract_fields(
            llm,
            name=new_entity.name,
            schema_name=new_entity.schema,
            schema_field_names=schema_field_names.get(new_entity.schema, []),
            doc_text=doc_text,
            target=target,
            source_doc_id=doc_id,
        )
        usage += u
        if field_set is not None:
            field_proposals.append(field_set)

    for link in approved_links:
        target = FieldSetTarget(
            name=link.entity_name, schema=link.schema, entity_id=link.entity_id
        )
        field_set, u = extract_fields(
            llm,
            name=link.entity_name,
            schema_name=link.schema,
            schema_field_names=schema_field_names.get(link.schema, []),
            doc_text=doc_text,
            target=target,
            source_doc_id=doc_id,
        )
        usage += u
        if field_set is not None:
            field_proposals.append(field_set)

    # 5. Review field-sets.
    approved_fields = [
        d.change for d in reviewer.review(field_proposals) if d.approved
    ]

    # 6. Build the final change list: new entities, then links, then field-sets.
    approved_changes: list[ProposedChange] = [
        *approved_new,
        *approved_links,
        *approved_fields,
    ]

    if dry_run:
        return ProcessResult(
            doc_id=doc_id,
            approved_changes=approved_changes,
            commit_report=None,
            usage=usage,
            dry_run=True,
        )

    report = commit_changes(root, doc_id, approved_changes)
    return ProcessResult(
        doc_id=doc_id,
        approved_changes=approved_changes,
        commit_report=report,
        usage=usage,
        dry_run=False,
    )

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
an :class:`~forte.services.agent._llm.LLMClient` and a
:class:`~forte.services.agent._review.Reviewer` (both injected) plus the vault root,
and returns a plain :class:`ProcessResult` that the CLI renders.

Failure semantics: if any pipeline step exhausts its retries it raises
:class:`~forte.services.agent._structured.StructuredCallError`, which propagates out of
``process_document`` uncaught. Because commit is the last thing that runs,
nothing has been written when a step fails — the run aborts with an empty vault
delta.

Ordering: approved entity proposals are presented and committed
new-entities-first, then links. This is also how ``approved_changes`` is
constructed (new entities, then links, then field-sets), which keeps each
:class:`~forte.services.agent._pipeline_models.FieldSetTarget.new_entity_ref` aligned
with :func:`~forte.services.agent._commit.commit_changes`' resolution scheme: commit
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
from forte.services.document import get_document
from forte.services.schema import list_schemas

from ._bulk_format import parse as parse_bulk
from ._bulk_format import render as render_bulk
from ._commit import CommitReport, commit_changes
from ._editor import EditorSession
from ._llm import LLMClient
from ._pipeline_models import (
    FieldSetTarget,
    ProposedChange,
    ProposedFieldSet,
    ProposedLink,
    ProposedNewEntity,
)
from ._review import Reviewer
from ._steps import extract_entities, extract_fields, resolve_candidate
from ._usage import Usage


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
    not exist, and lets :class:`~forte.services.agent._structured.StructuredCallError`
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


def process_document_bulk(
    root: Path,
    doc_id: int,
    *,
    llm: LLMClient,
    editor: EditorSession,
    dry_run: bool = False,
) -> ProcessResult:
    """Run the bulk-commit flow: one editor pass reviews EVERY proposal at once.

    This is a deliberate divergence from ``process_document``'s "option B"
    contract. Option B reviews entity proposals first and field-extracts ONLY
    the survivors, so a rejected entity never pays for a field-extraction call.
    Bulk mode collapses the two sequential review points into a SINGLE editor
    session, which means it must field-extract EVERY proposed entity (both new
    entities and links) UP FRONT, before the editor opens — there is no earlier
    review point to prune the set. That is strictly more LLM calls than option
    B; it is the intrinsic cost of showing the user everything in one pass.
    ``usage`` is accumulated across every one of those calls so the cost
    summary stays accurate.

    Flow:
      1. extract candidates and resolve each to a link/new-entity proposal;
      2. eagerly field-extract every proposed entity into ProposedFieldSets;
      3. render the full change list, hand it to ``editor.edit``, parse the
         edited text back into per-change decisions;
      4. build the approved set (see the promotion note below) and commit,
         honoring ``dry_run`` exactly like ``process_document``.

    ``new_entity_ref`` alignment / the promotion edge case
    ------------------------------------------------------
    Field-sets on NEW entities carry a ``new_entity_ref`` that indexes into the
    full ordered new-entity list built here. After the editor returns, the user
    may have rejected a new entity while approving a field-set that targets it.
    Such a field-set is useless with nowhere to land, so we PROMOTE the rejected
    ``ProposedNewEntity`` back into the approved set. Once promotions are
    resolved, the final ``approved_new`` list is a subset of the original new
    list (in original order); we then RE-ASSIGN every surviving field-set's
    ``new_entity_ref`` to that entity's position in the final list, so the
    indices still line up with :func:`commit_changes`' resolution scheme (which
    keys ``new_entity_ref`` by position among the ``ProposedNewEntity`` items in
    commit order).

    Raises :class:`~forte.services.document.DocumentNotFoundError` if ``doc_id``
    does not exist, lets :class:`~forte.services.agent._structured.StructuredCallError`
    propagate if a step exhausts its retries, and lets
    :class:`~forte.services.agent._editor.EditorAbortedError` propagate if the
    editor exits non-zero. In every failure case nothing is committed, because
    commit is the last step.
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

    # Order entity proposals new-entities-first, then links. The new list's
    # order fixes each new entity's new_entity_ref for the field-extraction
    # below (and the promotion remap after review).
    all_new = [p for p in entity_proposals if isinstance(p, ProposedNewEntity)]
    all_links = [p for p in entity_proposals if isinstance(p, ProposedLink)]

    # 3. EAGERLY field-extract EVERY proposed entity (new AND linked), not just
    #    approved ones — the intentional cost of one-pass review. New-entity
    #    field-sets key by new_entity_ref (index into all_new); link field-sets
    #    key by entity_id.
    all_fields: list[ProposedFieldSet] = []
    for index, new_entity in enumerate(all_new):
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
            all_fields.append(field_set)

    for link in all_links:
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
            all_fields.append(field_set)

    # 4. Assemble the full change list in a stable order (new, links, fields),
    #    render it, review it in one editor pass, and parse decisions back.
    #    render/parse key by position in this exact list, so it must not be
    #    reordered between the two calls.
    all_changes: list[ProposedChange] = [*all_new, *all_links, *all_fields]

    if not all_changes:
        # Nothing was proposed: do not open the editor at all. Honor dry_run.
        return _bulk_result(root, doc_id, [], usage, dry_run)

    edited = editor.edit(render_bulk(all_changes))  # EditorAbortedError propagates
    decisions = parse_bulk(edited, all_changes)
    approved = {id(d.change) for d in decisions if d.approved}

    # 5. Build the approved set, resolving the promotion edge case. First,
    #    which original new-entity indices are approved outright.
    approved_new_indices: set[int] = {
        index for index, new_entity in enumerate(all_new) if id(new_entity) in approved
    }
    approved_links = [link for link in all_links if id(link) in approved]
    approved_fields = [fs for fs in all_fields if id(fs) in approved]

    # PROMOTE: any approved field-set targeting a rejected new entity forces
    # that entity back into the approved set so its values have somewhere to go.
    for field_set in approved_fields:
        ref = field_set.target.new_entity_ref
        if ref is not None:
            approved_new_indices.add(ref)

    # Freeze the final new-entity ordering (original order preserved) and build
    # the old-index -> new-position remap for new_entity_ref realignment.
    final_new_indices = sorted(approved_new_indices)
    approved_new = [all_new[index] for index in final_new_indices]
    remap = {old: new for new, old in enumerate(final_new_indices)}

    # Realign each new-entity-targeted field-set's new_entity_ref to its
    # position in the final approved_new list (link-targeted sets are untouched).
    realigned_fields: list[ProposedChange] = []
    for field_set in approved_fields:
        ref = field_set.target.new_entity_ref
        if ref is None:
            realigned_fields.append(field_set)
            continue
        new_target = FieldSetTarget(
            name=field_set.target.name,
            schema=field_set.target.schema,
            new_entity_ref=remap[ref],
        )
        realigned_fields.append(
            ProposedFieldSet(
                target=new_target,
                fields=field_set.fields,
                source_doc_id=field_set.source_doc_id,
            )
        )

    approved_changes: list[ProposedChange] = [
        *approved_new,
        *approved_links,
        *realigned_fields,
    ]

    return _bulk_result(root, doc_id, approved_changes, usage, dry_run)


def _bulk_result(
    root: Path,
    doc_id: int,
    approved_changes: list[ProposedChange],
    usage: Usage,
    dry_run: bool,
) -> ProcessResult:
    """Commit ``approved_changes`` (or skip on dry-run) and wrap in a ProcessResult."""
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

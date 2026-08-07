"""Best-effort committer for the agent pipeline's approved proposed changes.

Writes approved :class:`~forte.model.agent.ProposedChange` objects through the
injected SERVICE layer (:class:`~forte.service.entity_service.EntityService` /
:class:`~forte.service.document_service.DocumentService`) so the markdown +
SQLite dual-write invariant holds — this module never touches markdown, SQLite,
or a storage client directly.

Commit is best-effort, not atomic: each change is attempted independently.
A failure on one change is caught and recorded in the returned
:class:`~forte.model.agent.CommitReport`; the rest proceed regardless.
"""

from __future__ import annotations

from forte.model.agent import (
    CommitReport,
    CommitResult,
    ProposedChange,
    ProposedFieldSet,
    ProposedLink,
    ProposedNewEntity,
)
from forte.service.document_service import DocumentService
from forte.service.entity_service import EntityService


def commit_changes(
    doc_id: int,
    changes: list[ProposedChange],
    *,
    document_service: DocumentService,
    entity_service: EntityService,
) -> CommitReport:
    """
    Commit approved ``changes`` for ``doc_id``, best-effort.

    Processing order: :class:`~forte.model.agent.ProposedNewEntity` first (so
    their ids exist for any field-sets/links that reference them), then
    :class:`~forte.model.agent.ProposedLink`, then
    :class:`~forte.model.agent.ProposedFieldSet`.

    Args:
        doc_id (int): The document every new entity / link is attributed to.
        changes (list[ProposedChange]): The approved changes to commit.
        document_service (DocumentService): Used to record doc-entity links.
        entity_service (EntityService): Used to create and edit entities.

    Returns:
        (CommitReport) A success/failure record per change, in the order the
            changes were attempted. Never raises for an individual change's
            failure.
    """
    report = CommitReport()

    new_entities = [c for c in changes if isinstance(c, ProposedNewEntity)]
    links = [c for c in changes if isinstance(c, ProposedLink)]
    field_sets = [c for c in changes if isinstance(c, ProposedFieldSet)]

    # index (position among ProposedNewEntity items in `changes`) -> new entity id
    new_entity_ids: dict[int, int] = {}

    for index, change in enumerate(new_entities):
        try:
            created = entity_service.add_entity(
                change.schema,
                change.name,
                aliases=change.aliases,
                field_values=change.fields,
            )
            new_entity_ids[index] = created.id
            document_service.link_document(
                doc_id, created.id, quote=change.supporting_quote
            )
            report.results.append(CommitResult(change=change, success=True))
        except Exception as exc:  # noqa: BLE001 - best-effort: record and continue
            report.results.append(CommitResult(change=change, success=False, error=str(exc)))

    for change in links:
        try:
            document_service.link_document(
                doc_id, change.entity_id, quote=change.supporting_quote
            )
            report.results.append(CommitResult(change=change, success=True))
        except Exception as exc:  # noqa: BLE001
            report.results.append(CommitResult(change=change, success=False, error=str(exc)))

    for change in field_sets:
        try:
            target = change.target
            if target.entity_id is not None:
                target_id = target.entity_id
            else:
                target_id = new_entity_ids[target.new_entity_ref]

            current = entity_service.get_entity(target_id)
            only_empty = {
                name: value
                for name, value in change.fields.items()
                if current.fields.get(name, "") == ""
            }
            if only_empty:
                entity_service.edit_entity(target_id, set_fields=only_empty)
            report.results.append(CommitResult(change=change, success=True))
        except Exception as exc:  # noqa: BLE001
            report.results.append(CommitResult(change=change, success=False, error=str(exc)))

    return report

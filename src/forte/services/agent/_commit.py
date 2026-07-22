"""Best-effort committer for the agent pipeline's approved proposed changes.

Writes approved :class:`~forte.services.pipeline_models.ProposedChange`
objects through the EXISTING service layer (``entity.py`` / ``document.py``)
so the markdown + SQLite dual-write invariant holds — this module never
touches markdown or SQLite directly.

Commit is best-effort, not atomic: each change is attempted independently.
A failure on one change is caught and recorded in the returned
:class:`CommitReport`; the rest proceed regardless.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from forte.services import document, entity
from forte.services.pipeline_models import (
    ProposedChange,
    ProposedFieldSet,
    ProposedLink,
    ProposedNewEntity,
)


@dataclass
class CommitResult:
    """The outcome of attempting to commit one proposed change."""

    change: ProposedChange
    success: bool
    error: str | None = None


@dataclass
class CommitReport:
    """The full record of a best-effort commit run."""

    results: list[CommitResult] = field(default_factory=list)

    @property
    def successes(self) -> list[CommitResult]:
        return [r for r in self.results if r.success]

    @property
    def failures(self) -> list[CommitResult]:
        return [r for r in self.results if not r.success]


def commit_changes(root: Path, doc_id: int, changes: list[ProposedChange]) -> CommitReport:
    """Commit approved ``changes`` for ``doc_id``, best-effort.

    Processing order: :class:`ProposedNewEntity` first (so their ids exist
    for any field-sets/links that reference them), then
    :class:`ProposedLink`, then :class:`ProposedFieldSet`.

    Returns a :class:`CommitReport` recording a success/failure per change;
    never raises for an individual change's failure.
    """
    report = CommitReport()

    new_entities = [c for c in changes if isinstance(c, ProposedNewEntity)]
    links = [c for c in changes if isinstance(c, ProposedLink)]
    field_sets = [c for c in changes if isinstance(c, ProposedFieldSet)]

    # index (position among ProposedNewEntity items in `changes`) -> new entity id
    new_entity_ids: dict[int, int] = {}

    for index, change in enumerate(new_entities):
        try:
            created = entity.add_entity(
                root,
                change.schema,
                change.name,
                aliases=change.aliases,
                field_values=change.fields,
            )
            new_entity_ids[index] = created.id
            document.link_document(root, doc_id, created.id, quote=change.supporting_quote)
            report.results.append(CommitResult(change=change, success=True))
        except Exception as exc:  # noqa: BLE001 - best-effort: record and continue
            report.results.append(CommitResult(change=change, success=False, error=str(exc)))

    for change in links:
        try:
            document.link_document(root, doc_id, change.entity_id, quote=change.supporting_quote)
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

            current = entity.get_entity(root, target_id)
            only_empty = {
                name: value
                for name, value in change.fields.items()
                if current.fields.get(name, "") == ""
            }
            if only_empty:
                entity.edit_entity(root, target_id, set_fields=only_empty)
            report.results.append(CommitResult(change=change, success=True))
        except Exception as exc:  # noqa: BLE001
            report.results.append(CommitResult(change=change, success=False, error=str(exc)))

    return report

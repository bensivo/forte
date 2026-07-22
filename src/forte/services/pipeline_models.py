"""In-memory domain models for the agent pipeline.

These dataclasses are the vocabulary the whole agent pipeline speaks: the
extract-entities step, the linking step, the field-extraction step, the
reviewer, the orchestrator, and the committer all pass these types between
each other. They are plain data — no Click, no Rich, no DB/SQLite imports, no
repository access — so they are trivially serializable and a future web layer
can send them over a request/response boundary unchanged.

IMPORTANT: :class:`RunState` is IN-MEMORY ONLY. There is no ``ingest_changes``
table, no persistence, and no resume support. If the process is interrupted
(e.g. Ctrl-C) the entire run state is dropped — that is intended behavior for
the MVP, not a gap to fill in later.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from forte.services.usage import Usage


@dataclass
class CandidateEntity:
    """An entity mention extracted from a document, before linking.

    Produced by the extract-entities step. Not yet tied to an existing
    entity or confirmed as a new one — that happens in the linking step.
    """

    name: str
    schema: str
    supporting_quote: str


@dataclass
class ProposedNewEntity:
    """A proposal to create a brand-new entity."""

    name: str
    schema: str
    supporting_quote: str
    aliases: list[str] = field(default_factory=list)
    fields: dict[str, str] = field(default_factory=dict)


@dataclass
class ProposedLink:
    """A proposal to link an extracted candidate to an EXISTING entity."""

    entity_id: int
    entity_name: str
    schema: str
    candidate_name: str
    supporting_quote: str


@dataclass
class FieldSetTarget:
    """The entity a :class:`ProposedFieldSet` applies to.

    Invariant: exactly one of ``entity_id`` / ``new_entity_ref`` is set.
    ``entity_id`` is used when the entity already exists (or has already been
    committed earlier in this run); ``new_entity_ref`` is an index into the
    run's approved :class:`ProposedNewEntity` list, used when the entity is
    being created as part of this same run. ``name``/``schema`` are carried
    along purely for display purposes (e.g. in a review UI).
    """

    name: str
    schema: str
    entity_id: int | None = None
    new_entity_ref: int | None = None

    def is_valid(self) -> bool:
        """Return True iff exactly one of entity_id/new_entity_ref is set."""
        return (self.entity_id is None) != (self.new_entity_ref is None)


@dataclass
class ProposedFieldSet:
    """A proposal to set schema-field values on one entity.

    The target entity may be pre-existing or newly created this run — see
    :class:`FieldSetTarget`. ``source_doc_id`` records which document the
    field values were extracted from.
    """

    target: FieldSetTarget
    fields: dict[str, str]
    source_doc_id: int


# The three atomic, independently-approvable proposed-change kinds.
ProposedChange = ProposedNewEntity | ProposedLink | ProposedFieldSet


class RunStage(enum.Enum):
    """The stage of an in-progress ``agent process`` run."""

    EXTRACTING = "extracting"
    REVIEW_ENTITIES = "review_entities"
    LINKING = "linking"
    REVIEW_LINKS = "review_links"
    EXTRACTING_FIELDS = "extracting_fields"
    REVIEW_FIELDS = "review_fields"
    COMMITTING = "committing"
    DONE = "done"


@dataclass
class Decision:
    """A proposed change together with the reviewer's approve/reject call."""

    change: ProposedChange
    approved: bool


@dataclass
class RunState:
    """The entire in-memory state of one ``agent process`` run.

    IN-MEMORY ONLY: no persistence, no resume. See module docstring.
    """

    doc_id: int
    stage: RunStage = RunStage.EXTRACTING
    candidates: list[CandidateEntity] = field(default_factory=list)
    proposed_links: list[ProposedLink] = field(default_factory=list)
    proposed_new_entities: list[ProposedNewEntity] = field(default_factory=list)
    proposed_field_sets: list[ProposedFieldSet] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage.zero)

    def add_usage(self, u: Usage) -> None:
        """Accumulate ``u`` into this run's total usage.

        Usage is frozen, so this reassigns ``self.usage`` to a new summed
        instance rather than mutating in place.
        """
        self.usage = self.usage + u

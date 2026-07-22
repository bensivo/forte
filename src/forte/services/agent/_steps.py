"""The three LLM pipeline steps, each a discrete structured call.

These are pure functions of ``(llm + data)``: no Click/Rich, no DB writes, no
vault-root/repository access. Each step runs exactly one bounded-retry
``structured_call`` (or, for the no-candidate case in ``resolve_candidate``, no
call at all) and returns its proposed change(s) plus the token
:class:`~forte.services.agent._usage.Usage` of the call, so the orchestrator can
accumulate usage across the run.

The steps compose the prompt templates + parse functions in
:mod:`forte.services.agent._prompts` with the reusable retry helper in
:mod:`forte.services.agent._structured`. Semantic, non-error filtering that must NOT
trigger a retry (dropping unknown-schema candidates; dropping unsupported field
values) lives here, after a successful parse — never inside the parse callback.
"""

from __future__ import annotations

from forte.domain.entity import Entity
from forte.services.linking import find_candidates

from ._llm import LLMClient
from ._pipeline_models import (
    CandidateEntity,
    FieldSetTarget,
    ProposedFieldSet,
    ProposedLink,
    ProposedNewEntity,
)
from ._prompts import (
    EXTRACTION_SCHEMA,
    EXTRACTION_SYSTEM,
    FIELD_SYSTEM,
    LINK_SCHEMA,
    LINK_SYSTEM,
    build_extraction_user,
    build_field_schema,
    build_field_user,
    build_link_user,
    make_field_parser,
    make_link_parser,
    parse_extraction,
)
from ._structured import structured_call
from ._usage import Usage


def extract_entities(
    llm: LLMClient, *, doc_text: str, schema_names: list[str]
) -> tuple[list[CandidateEntity], Usage]:
    """Extract candidate entities from ``doc_text`` (step 2 of the pipeline).

    Runs the extraction prompt via ``structured_call`` (5-retry on malformed
    output), then DROPS any candidate whose schema is not in ``schema_names`` —
    a post-parse, non-error filter, so an unknown-schema candidate never causes
    a retry. An empty list is a valid result. Returns the surviving candidates
    plus the call's usage.
    """
    candidates, usage = structured_call(
        llm,
        system=EXTRACTION_SYSTEM,
        user=build_extraction_user(doc_text, schema_names),
        schema=EXTRACTION_SCHEMA,
        parse=parse_extraction,
    )
    allowed = set(schema_names)
    kept = [c for c in candidates if c.schema in allowed]
    return kept, usage


def _new_entity(candidate: CandidateEntity) -> ProposedNewEntity:
    """Build a new-entity proposal from an unlinked candidate."""
    return ProposedNewEntity(
        name=candidate.name,
        schema=candidate.schema,
        supporting_quote=candidate.supporting_quote,
    )


def resolve_candidate(
    llm: LLMClient,
    *,
    candidate: CandidateEntity,
    doc_text: str,
    existing_entities: list[Entity],
) -> tuple[ProposedLink | ProposedNewEntity, Usage]:
    """Resolve one candidate to a link or a new-entity proposal (step 3+4 fused).

    Runs the deterministic rule-based matcher (:func:`find_candidates`) first.
    If it finds NO existing entities, returns a :class:`ProposedNewEntity`
    WITHOUT any LLM call (``Usage.zero()``) — the cost/latency win. Otherwise
    calls the link prompt to pick one of the offered ids or "none":
      - a chosen id -> :class:`ProposedLink` carrying the entity id/name/schema,
        the candidate name, and the candidate's supporting quote;
      - null / "none" -> :class:`ProposedNewEntity`.
    An id returned outside the offered set is rejected by the parser (retryable).
    """
    matches = find_candidates(candidate.name, candidate.schema, existing_entities)
    if not matches:
        return _new_entity(candidate), Usage.zero()

    allowed_ids = [e.id for e in matches if e.id is not None]
    chosen_id, usage = structured_call(
        llm,
        system=LINK_SYSTEM,
        user=build_link_user(candidate, doc_text, matches),
        schema=LINK_SCHEMA,
        parse=make_link_parser(allowed_ids),
    )
    if chosen_id is None:
        return _new_entity(candidate), usage

    matched = next(e for e in matches if e.id == chosen_id)
    link = ProposedLink(
        entity_id=chosen_id,
        entity_name=matched.name,
        schema=candidate.schema,
        candidate_name=candidate.name,
        supporting_quote=candidate.supporting_quote,
    )
    return link, usage


def extract_fields(
    llm: LLMClient,
    *,
    name: str,
    schema_name: str,
    schema_field_names: list[str],
    doc_text: str,
    target: FieldSetTarget,
    source_doc_id: int,
) -> tuple[ProposedFieldSet | None, Usage]:
    """Extract schema field values for one entity (step 5 of the pipeline).

    Only proposes values for keys in ``schema_field_names`` (enforced by the
    parser). Empty-string values (the model's "not supported by the document"
    signal) are dropped post-parse. Returns ``None`` when nothing is
    extractable — an empty schema (no declared fields), or every value empty —
    in which case NO change is proposed and the orchestrator skips this entity.
    Otherwise returns a :class:`ProposedFieldSet` on ``target`` tagged with
    ``source_doc_id``.

    ``source_doc_id`` is passed in explicitly (``FieldSetTarget`` does not carry
    it) and stored on the returned :class:`ProposedFieldSet` for future
    field-value provenance work; a field with no declared fields makes no call.
    """
    if not schema_field_names:
        return None, Usage.zero()

    raw, usage = structured_call(
        llm,
        system=FIELD_SYSTEM,
        user=build_field_user(name, schema_name, schema_field_names, doc_text),
        schema=build_field_schema(schema_field_names),
        parse=make_field_parser(schema_field_names),
    )
    fields = {key: value for key, value in raw.items() if value.strip()}
    if not fields:
        return None, usage
    return ProposedFieldSet(target=target, fields=fields, source_doc_id=source_doc_id), usage

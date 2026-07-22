"""Rule-based, non-LLM candidate matching for entity linking.

This is core, free `forte` infrastructure (not under the `forte agent`
namespace) — it costs nothing to run and is used to discover candidate
existing entities that a newly-extracted candidate might refer to. The
*decision* of which candidate (if any) is correct is left to a later,
LLM-backed step; this module only narrows the field deterministically.
"""

from __future__ import annotations

import re

from forte.domain.entity import Entity


def _normalize(s: str) -> str:
    """Lowercase, collapse internal whitespace, and strip.

    Used to compare names/aliases in a case- and whitespace-insensitive way.
    """
    return re.sub(r"\s+", " ", s.strip().lower())


def find_candidates(
    candidate_name: str, candidate_schema: str, entities: list[Entity]
) -> list[Entity]:
    """Return existing entities that plausibly match a candidate.

    Matching rules, applied in order (any one is sufficient for a match):
      1. Exact name match (case-sensitive).
      2. Exact alias match (case-sensitive).
      3. Case/whitespace-normalized match on name or any alias — lowercased,
         internal whitespace collapsed to a single space, and stripped.

    Scoping: matching is restricted to entities whose ``schema`` equals
    ``candidate_schema``. A candidate named "Apollo" classified as a Person
    must never match a Project entity also named "Apollo" — schema identity
    is part of what makes two entities "the same thing" here. Cross-schema
    matching is intentionally not supported.

    Returns an empty list when nothing matches — the signal that the
    candidate should become a new entity. The returned list is de-duplicated
    (an entity matching on multiple rules appears once) and stably ordered
    by entity id.

    This is a pure function of its arguments: it takes no LLM client and
    performs no I/O / DB queries. Callers are responsible for supplying the
    entities list (e.g. via ``EntityRepository(root).list()``).

    Future extension point: a vector/embedding-based candidate source is
    deferred for now, but would union its results into this candidate set
    here (still subject to the same schema scoping) rather than replacing
    the rule-based pass.
    """
    normalized_candidate = _normalize(candidate_name)

    matches: dict[int | None, Entity] = {}
    for entity in entities:
        if entity.schema != candidate_schema:
            continue

        is_match = (
            entity.name == candidate_name
            or candidate_name in entity.aliases
            or _normalize(entity.name) == normalized_candidate
            or any(_normalize(alias) == normalized_candidate for alias in entity.aliases)
        )
        if is_match:
            matches[entity.id] = entity

    # --- future seam ---
    # A future embeddings/vector-based candidate source would compute its own
    # set of plausible entities here and union it into `matches` (still
    # filtered to `candidate_schema`), e.g.:
    #     for entity in vector_candidates(candidate_name, candidate_schema, entities):
    #         matches[entity.id] = entity
    # Embeddings are deferred for the MVP; rule-based matching only.

    return sorted(matches.values(), key=lambda e: (e.id is None, e.id))

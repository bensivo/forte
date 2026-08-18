from __future__ import annotations

import re

from forte.interface.document_db import IDocumentDb
from forte.interface.entity_db import IEntityDb
from forte.interface.mention_db import IMentionDb
from forte.interface.schema_db import ISchemaDb
from forte.model.document import Document
from forte.model.entity import (
    Entity,
    EntityNotFoundError,
    InvalidEntityError,
    UnknownSchemaError,
)


def _apply_field_set(schema_fields: list[str], values: dict[str, str]) -> dict[str, str]:
    """Return a fields dict carrying exactly the schema's fields, in order.

    Values present in ``values`` are used; any omitted schema field is
    back-filled with an empty string. Callers must have already validated that
    ``values`` contains no fields outside ``schema_fields``.
    """
    return {name: values.get(name, "") for name in schema_fields}


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
    entities list (e.g. via ``EntityService.list_entities()``).

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


def _search_rank(entity: Entity, normalized_query: str) -> tuple[int, int, int] | None:
    """Return the sort key for ``entity`` against ``normalized_query``, or
    ``None`` if it does not match.

    The key is ``(name_rank, prefix_rank, entity_id)``:
      - ``name_rank`` is 0 when the query matches the entity's name, 1 when
        it only matches an alias — name matches sort first.
      - ``prefix_rank`` is 0 when the (best) matching field starts with the
        query, 1 for a mid-string match — prefix matches sort first.
      - ``entity_id`` is the final, deterministic tiebreak.

    An empty ``normalized_query`` matches every entity (as a prefix match on
    the name), which is what backs "show everything before typing anything".
    """
    entity_id = entity.id if entity.id is not None else -1

    def field_rank(value: str) -> int | None:
        normalized_value = _normalize(value)
        if normalized_query not in normalized_value:
            return None
        return 0 if normalized_value.startswith(normalized_query) else 1

    name_prefix_rank = field_rank(entity.name)
    if name_prefix_rank is not None:
        return (0, name_prefix_rank, entity_id)

    best_alias_rank: int | None = None
    for alias in entity.aliases:
        alias_rank = field_rank(alias)
        if alias_rank is not None and (best_alias_rank is None or alias_rank < best_alias_rank):
            best_alias_rank = alias_rank
            if best_alias_rank == 0:
                break

    if best_alias_rank is not None:
        return (1, best_alias_rank, entity_id)

    return None


class EntityService:
    """
    Contains all the operations that can be performed on entities: create,
    list, show, edit, and remove. The core rule enforced here is the
    **structural field-set invariant**: every entity of a schema carries
    *exactly* that schema's user-defined field set (no missing, no extra
    fields), in schema field order, with the built-in ``name``/``aliases``
    kept separate. Field *values* are free-text strings and all optional —
    only the *set* of field names is constrained.
    """

    def __init__(
        self,
        entity_db: IEntityDb,
        schema_db: ISchemaDb,
        mention_db: IMentionDb,
        document_db: IDocumentDb,
    ):
        """
        Args:
            entity_db (IEntityDb): Storage backend for entity persistence.
            schema_db (ISchemaDb): Storage backend used to look up the
                authoritative field set for an entity's schema.
            mention_db (IMentionDb): Storage backend used to look up an
                entity's doc-entity mention links.
            document_db (IDocumentDb): Storage backend used to resolve a
                mention's document id to a document.
        """
        self.entity_db = entity_db
        self.schema_db = schema_db
        self.mention_db = mention_db
        self.document_db = document_db

    def add_entity(
        self,
        schema: str,
        name: str,
        aliases: list[str] | None = None,
        field_values: dict[str, str] | None = None,
    ) -> Entity:
        """
        Validate and create a new entity of ``schema``.

        Args:
            schema (str): Name of the schema this entity belongs to.
            name (str): The entity's name.
            aliases (list[str] | None): Alternate names for the entity.
            field_values (dict[str, str] | None): Values for the schema's
                fields. Omitted fields are back-filled with ``""`` so the
                stored entity carries exactly the schema's field set (in
                schema field order).

        Returns:
            (Entity) The created entity, with its assigned id.

        Raises:
            UnknownSchemaError: if no schema named ``schema`` exists.
            InvalidEntityError: if ``name`` is missing/empty, or
                ``field_values`` names a field the schema does not declare.
        """
        aliases = list(aliases or [])
        field_values = dict(field_values or {})

        schema_obj = self.schema_db.get(schema)
        if schema_obj is None:
            raise UnknownSchemaError(f"Schema {schema!r} does not exist.")
        schema_fields = [f.name for f in schema_obj.fields]

        if not name or not name.strip():
            raise InvalidEntityError("Entity name is required and must not be empty.")

        unknown = [f for f in field_values if f not in schema_fields]
        if unknown:
            raise InvalidEntityError(
                f"Unknown field(s) for schema {schema!r}: "
                f"{', '.join(sorted(unknown))}. "
                f"Allowed fields: {', '.join(schema_fields) or '(none)'}."
            )

        fields = _apply_field_set(schema_fields, field_values)

        entity = Entity(schema=schema, name=name, aliases=aliases, fields=fields)
        return self.entity_db.add(entity)

    def list_entities(self, schema: str | None = None) -> list[Entity]:
        """
        Return all entities, or only those of ``schema``, ordered by id.

        Args:
            schema (str | None): If given, only entities of this schema are
                returned.

        Returns:
            (list[Entity]) The matching entities, ordered by id.

        Raises:
            UnknownSchemaError: if ``schema`` is given but does not exist
                (rather than silently returning an empty list, which would
                mask a typo).
        """
        if schema is not None and self.schema_db.get(schema) is None:
            raise UnknownSchemaError(f"Schema {schema!r} does not exist.")
        return self.entity_db.list(schema=schema)

    def search_entities(self, query: str, *, limit: int | None = None) -> list[Entity]:
        """
        Return entities whose name or any alias contains ``query`` as a
        case-insensitive substring, across all schemas.

        ``query`` is normalized the same way names/aliases are compared
        elsewhere (lowercased, internal whitespace collapsed, stripped)
        before matching, so ``"  ali "`` and ``"ali"`` behave identically.
        An empty or whitespace-only query matches every entity, which backs
        the "show me everything before I've typed anything" state of the
        interactive prompt.

        Results are ranked deterministically: name matches before
        alias-only matches, prefix matches before mid-string matches, then
        ascending entity id as the final tiebreak. Each entity appears at
        most once, even if it matches on both its name and an alias.

        Args:
            query (str): The substring to search for.
            limit (int | None): If given, caps the number of results
                returned, applied after ranking.

        Returns:
            (list[Entity]) The matching entities, ranked as described above.
        """
        normalized_query = _normalize(query)

        ranked: list[tuple[tuple[int, int, int], Entity]] = []
        for entity in self.entity_db.list():
            rank = _search_rank(entity, normalized_query)
            if rank is not None:
                ranked.append((rank, entity))

        ranked.sort(key=lambda pair: pair[0])
        results = [entity for _, entity in ranked]

        if limit is not None:
            results = results[:limit]
        return results

    def get_entity(self, id: int) -> Entity:
        """
        Return the entity with the given id.

        Args:
            id (int): The entity id to look up.

        Returns:
            (Entity) The matching entity.

        Raises:
            EntityNotFoundError: if no entity with that id exists.
        """
        entity = self.entity_db.get(id)
        if entity is None:
            raise EntityNotFoundError(f"Entity #{id} does not exist.")
        return entity

    def list_mentioning_documents(self, id: int) -> list[Document]:
        """
        Return the documents that mention an entity, ordered by document id.

        Reads the entity's mentions and resolves each one to its document.
        A mention pointing at a document that no longer exists is skipped
        rather than raising, so a stale row can never make ``entity show``
        fail.

        Args:
            id (int): The entity id whose mentioning documents to list.

        Returns:
            (list[Document]) The mentioning documents, ordered by document id.

        Raises:
            EntityNotFoundError: if no entity with that id exists.
        """
        if self.entity_db.get(id) is None:
            raise EntityNotFoundError(f"Entity #{id} does not exist.")

        documents: list[Document] = []
        for mention in self.mention_db.list_for_entity(id):
            document = self.document_db.get(mention.doc_id)
            if document is not None:
                documents.append(document)
        return sorted(documents, key=lambda d: d.id or 0)

    def edit_entity(
        self,
        id: int,
        name: str | None = None,
        set_fields: dict[str, str] | None = None,
        add_aliases: list[str] | None = None,
        remove_aliases: list[str] | None = None,
    ) -> Entity:
        """
        Edit an existing entity.

        Supports renaming (``name``), setting values for existing schema
        fields (``set_fields``), and adding/removing aliases
        (``add_aliases`` / ``remove_aliases``). Re-applies the structural
        invariant so the field set stays exactly the schema's. Validation
        happens before any write.

        Args:
            id (int): The entity id to edit.
            name (str | None): New name for the entity, if renaming.
            set_fields (dict[str, str] | None): Field values to set.
            add_aliases (list[str] | None): Aliases to add.
            remove_aliases (list[str] | None): Aliases to remove.

        Returns:
            (Entity) The updated entity.

        Raises:
            EntityNotFoundError: if no entity with that id exists.
            InvalidEntityError: if the new ``name`` is empty, or
                ``set_fields`` names a field the schema does not declare.
            UnknownSchemaError: if the entity's schema no longer exists.
        """
        set_fields = dict(set_fields or {})
        add_aliases = list(add_aliases or [])
        remove_aliases = list(remove_aliases or [])

        entity = self.entity_db.get(id)
        if entity is None:
            raise EntityNotFoundError(f"Entity #{id} does not exist.")

        schema_obj = self.schema_db.get(entity.schema)
        if schema_obj is None:
            raise UnknownSchemaError(f"Schema {entity.schema!r} does not exist.")
        schema_fields = [f.name for f in schema_obj.fields]

        if name is not None and not name.strip():
            raise InvalidEntityError("Entity name must not be empty.")

        unknown = [f for f in set_fields if f not in schema_fields]
        if unknown:
            raise InvalidEntityError(
                f"Unknown field(s) for schema {entity.schema!r}: "
                f"{', '.join(sorted(unknown))}. "
                f"Allowed fields: {', '.join(schema_fields) or '(none)'}."
            )

        # All validation passed — apply changes.
        if name is not None:
            entity.name = name

        merged = dict(entity.fields)
        merged.update(set_fields)
        # Re-apply the structural invariant against the current schema field set.
        entity.fields = _apply_field_set(schema_fields, merged)

        aliases = list(entity.aliases)
        for alias in add_aliases:
            if alias not in aliases:
                aliases.append(alias)
        for alias in remove_aliases:
            if alias in aliases:
                aliases.remove(alias)
        entity.aliases = aliases

        self.entity_db.update(entity)
        return entity

    def remove_entity(self, id: int) -> None:
        """
        Remove the entity with the given id.

        Args:
            id (int): The entity id to remove.

        Returns:
            None

        Raises:
            EntityNotFoundError: if no entity with that id exists.
        """
        if self.entity_db.get(id) is None:
            raise EntityNotFoundError(f"Entity #{id} does not exist.")
        self.entity_db.remove(id)

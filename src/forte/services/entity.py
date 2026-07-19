"""Service layer: create, list, show, edit, and remove entities in a vault.

All business rules for entities live here. The core rule is the **structural
field-set invariant**: every entity of a schema carries *exactly* that schema's
user-defined field set (no missing, no extra fields), in schema field order,
with the built-in ``name``/``aliases`` kept separate. Field *values* are
free-text strings and all optional — only the *set* of field names is
constrained.

The DB layer (`EntityRepository`) handles the dual-write (markdown + SQLite),
`SchemaRepository` supplies the authoritative field set, and the CLI layer maps
the typed exceptions raised here to Click errors.
"""

from __future__ import annotations

from pathlib import Path

from forte.db.entity_repository import EntityRepository
from forte.db.schema_repository import SchemaRepository
from forte.domain.entity import Entity


class EntityError(Exception):
    """Base class for entity service errors."""


class InvalidEntityError(EntityError):
    """Raised when an entity fails validation (missing name, unknown field)."""


class UnknownSchemaError(EntityError):
    """Raised when an operation references a schema that does not exist."""


class EntityNotFoundError(EntityError):
    """Raised when operating on an entity id that does not exist."""


def _apply_field_set(schema_fields: list[str], values: dict[str, str]) -> dict[str, str]:
    """Return a fields dict carrying exactly the schema's fields, in order.

    Values present in ``values`` are used; any omitted schema field is
    back-filled with an empty string. Callers must have already validated that
    ``values`` contains no fields outside ``schema_fields``.
    """
    return {name: values.get(name, "") for name in schema_fields}


def add_entity(
    root: Path,
    schema: str,
    name: str,
    aliases: list[str] | None = None,
    field_values: dict[str, str] | None = None,
) -> Entity:
    """Validate and create a new entity of ``schema`` in the vault at ``root``.

    Validation happens before any write. Raises:
      - UnknownSchemaError: no schema named ``schema`` exists.
      - InvalidEntityError: ``name`` is missing/empty, or ``field_values``
        names a field the schema does not declare.

    Omitted schema fields are back-filled with ``""`` so the stored entity
    carries exactly the schema's field set (in schema field order). Returns the
    created :class:`Entity` with its assigned id.
    """
    aliases = list(aliases or [])
    field_values = dict(field_values or {})

    schema_obj = SchemaRepository(root).get(schema)
    if schema_obj is None:
        raise UnknownSchemaError(f"Schema {schema!r} does not exist.")

    if not name or not name.strip():
        raise InvalidEntityError("Entity name is required and must not be empty.")

    unknown = [f for f in field_values if f not in schema_obj.fields]
    if unknown:
        raise InvalidEntityError(
            f"Unknown field(s) for schema {schema!r}: "
            f"{', '.join(sorted(unknown))}. "
            f"Allowed fields: {', '.join(schema_obj.fields) or '(none)'}."
        )

    fields = _apply_field_set(schema_obj.fields, field_values)

    entity = Entity(schema=schema, name=name, aliases=aliases, fields=fields)
    return EntityRepository(root).add(entity)


def list_entities(root: Path, schema: str | None = None) -> list[Entity]:
    """Return all entities, or only those of ``schema``, ordered by id.

    Raises UnknownSchemaError if ``schema`` is given but does not exist (rather
    than silently returning an empty list, which would mask a typo).
    """
    if schema is not None and not SchemaRepository(root).exists(schema):
        raise UnknownSchemaError(f"Schema {schema!r} does not exist.")
    return EntityRepository(root).list(schema=schema)


def get_entity(root: Path, id: int) -> Entity:
    """Return the entity with the given id, or raise EntityNotFoundError."""
    entity = EntityRepository(root).get(id)
    if entity is None:
        raise EntityNotFoundError(f"Entity #{id} does not exist.")
    return entity


def edit_entity(
    root: Path,
    id: int,
    name: str | None = None,
    set_fields: dict[str, str] | None = None,
    add_aliases: list[str] | None = None,
    remove_aliases: list[str] | None = None,
) -> Entity:
    """Edit an existing entity, dual-writing markdown + DB via the repository.

    Supports renaming (``name``), setting values for existing schema fields
    (``set_fields``), and adding/removing aliases (``add_aliases`` /
    ``remove_aliases``). Re-applies the structural invariant so the field set
    stays exactly the schema's. Validation happens before any write. Raises:
      - EntityNotFoundError: no entity with that id.
      - InvalidEntityError: new ``name`` is empty, or ``set_fields`` names a
        field the schema does not declare.
      - UnknownSchemaError: the entity's schema no longer exists.

    Returns the updated :class:`Entity`.
    """
    set_fields = dict(set_fields or {})
    add_aliases = list(add_aliases or [])
    remove_aliases = list(remove_aliases or [])

    repo = EntityRepository(root)
    entity = repo.get(id)
    if entity is None:
        raise EntityNotFoundError(f"Entity #{id} does not exist.")

    schema_obj = SchemaRepository(root).get(entity.schema)
    if schema_obj is None:
        raise UnknownSchemaError(f"Schema {entity.schema!r} does not exist.")

    if name is not None and not name.strip():
        raise InvalidEntityError("Entity name must not be empty.")

    unknown = [f for f in set_fields if f not in schema_obj.fields]
    if unknown:
        raise InvalidEntityError(
            f"Unknown field(s) for schema {entity.schema!r}: "
            f"{', '.join(sorted(unknown))}. "
            f"Allowed fields: {', '.join(schema_obj.fields) or '(none)'}."
        )

    # All validation passed — apply changes.
    if name is not None:
        entity.name = name

    merged = dict(entity.fields)
    merged.update(set_fields)
    # Re-apply the structural invariant against the current schema field set.
    entity.fields = _apply_field_set(schema_obj.fields, merged)

    aliases = list(entity.aliases)
    for alias in add_aliases:
        if alias not in aliases:
            aliases.append(alias)
    for alias in remove_aliases:
        if alias in aliases:
            aliases.remove(alias)
    entity.aliases = aliases

    repo.update(entity)
    return entity


def remove_entity(root: Path, id: int) -> None:
    """Remove the entity with the given id, or raise EntityNotFoundError."""
    repo = EntityRepository(root)
    if repo.get(id) is None:
        raise EntityNotFoundError(f"Entity #{id} does not exist.")
    repo.remove(id)

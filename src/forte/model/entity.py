from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Entity:
    """A single knowledge-base entity: one node in the knowledge graph.

    ``name`` and ``aliases`` are built-in *structural* fields and are kept
    separate from ``fields`` (the schema's user-defined fields). ``id`` and
    ``file_path`` are not stored inside the markdown frontmatter — they come
    from the DB row and the file's location.
    """

    schema: str
    name: str
    aliases: list[str] = field(default_factory=list)
    # Ordered to match the schema's field order; values are free-text strings.
    fields: dict[str, str] = field(default_factory=dict)
    body: str = ""
    id: int | None = None
    file_path: str | None = None


class EntityError(Exception):
    """Base class for entity service errors."""


class InvalidEntityError(EntityError):
    """Raised when an entity fails validation (missing name, unknown field)."""


class UnknownSchemaError(EntityError):
    """Raised when an operation references a schema that does not exist."""


class EntityNotFoundError(EntityError):
    """Raised when operating on an entity id that does not exist."""

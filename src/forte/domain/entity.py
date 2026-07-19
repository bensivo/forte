"""Entity domain model.

An entity is one node in the knowledge graph: a named thing of a given schema,
carrying the built-in structural fields ``name``/``aliases`` plus that schema's
user-defined fields, and an optional free-form markdown body.

Pure data — no filesystem or DB I/O happens here. Serialization to markdown
lives in :mod:`forte.domain.entity_markdown`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Entity:
    """A single knowledge-base entity.

    ``name`` and ``aliases`` are built-in *structural* fields and are kept
    separate from ``fields`` (the schema's user-defined fields). ``id``,
    ``schema``, and ``file_path`` are not stored inside the markdown
    frontmatter — they come from the DB row and the file's location.
    """

    schema: str
    name: str
    aliases: list[str] = field(default_factory=list)
    # Ordered to match the schema's field order; values are free-text strings.
    fields: dict[str, str] = field(default_factory=dict)
    body: str = ""
    id: int | None = None
    file_path: str | None = None

"""Service layer: define, list, and remove entity schemas in a vault.

All business rules for schemas live here (validation, existence checks,
in-use guards). The DB layer (`SchemaRepository`) handles persistence, and the
CLI layer maps the typed exceptions raised here to Click errors.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from forte.db.schema_repository import SchemaRepository
from forte.domain.schema import Schema
from forte.domain.vault import VaultLayout

# Built-in structural fields that every entity carries; user fields may not
# reuse these names.
_RESERVED_FIELDS = frozenset({"name", "aliases"})

# Folder-safe slug: lowercase alphanumerics plus hyphen/underscore, non-empty.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class SchemaError(Exception):
    """Base class for schema service errors."""


class InvalidSchemaError(SchemaError):
    """Raised when a schema name or its fields fail validation."""


class SchemaExistsError(SchemaError):
    """Raised when adding a schema whose name is already defined."""


class SchemaNotFoundError(SchemaError):
    """Raised when operating on a schema that does not exist."""


class SchemaInUseError(SchemaError):
    """Raised when removing a schema that still has entities."""


def add_schema(root: Path, name: str, fields: list[str]) -> Schema:
    """Validate and define a new schema in the vault rooted at ``root``.

    Validation happens before any write. Raises:
      - InvalidSchemaError: bad slug, reserved field, duplicate/empty field.
      - SchemaExistsError: a schema with that name already exists.
    Returns the created :class:`Schema` on success.
    """
    if not _SLUG_RE.match(name):
        raise InvalidSchemaError(
            f"Invalid schema name {name!r}: use lowercase letters, digits, "
            "hyphens, or underscores only (no spaces, slashes, or uppercase)."
        )

    for f in fields:
        if not f or not f.strip():
            raise InvalidSchemaError("Field names must not be empty or whitespace.")
        if f in _RESERVED_FIELDS:
            raise InvalidSchemaError(
                f"Field {f!r} is a reserved built-in field and cannot be redefined."
            )

    seen: set[str] = set()
    for f in fields:
        if f in seen:
            raise InvalidSchemaError(f"Duplicate field name {f!r} in schema {name!r}.")
        seen.add(f)

    repo = SchemaRepository(root)
    if repo.exists(name):
        raise SchemaExistsError(f"Schema {name!r} already exists.")

    schema = Schema(name=name, fields=list(fields))
    repo.add(schema)
    return schema


def list_schemas(root: Path) -> list[Schema]:
    """Return all schemas defined in the vault, ordered by name."""
    return SchemaRepository(root).list()


def remove_schema(root: Path, name: str) -> None:
    """Remove a schema from the vault rooted at ``root``.

    Raises:
      - SchemaNotFoundError: the schema does not exist.
      - SchemaInUseError: entities of that schema still exist.
    """
    repo = SchemaRepository(root)
    if not repo.exists(name):
        raise SchemaNotFoundError(f"Schema {name!r} does not exist.")

    if _entity_count(root, name) > 0:
        raise SchemaInUseError(
            f"Schema {name!r} still has entities. Remove those entities first."
        )

    repo.remove(name)


def _entity_count(root: Path, name: str) -> int:
    """Return how many entities of the given schema exist in the vault."""
    db_path = VaultLayout(root).db_path
    conn = sqlite3.connect(db_path)
    try:
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM entities WHERE schema = ?",
            (name,),
        ).fetchone()
    finally:
        conn.close()
    return count

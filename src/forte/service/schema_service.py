import re

from forte.interface.schema_db import ISchemaDb
from forte.model.schema import (
    InvalidSchemaError,
    Schema,
    SchemaExistsError,
    SchemaField,
    SchemaInUseError,
    SchemaNotFoundError,
)

# Built-in structural fields that every entity carries; user fields may not
# reuse these names.
_RESERVED_FIELDS = frozenset({"name", "aliases"})

# Folder-safe slug: lowercase alphanumerics plus hyphen/underscore, non-empty.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class SchemaService:
    """
    Contains all the operations that can be performed on schemas, including basic CRUD operations,
    and other non-CRUD features (like counting the number of entiteis in a schema)
    """

    def __init__(self, schema_db: ISchemaDb):
        """
        Args:
            schema_db (ISchemaDb): Storage backend for schema persistence.
        """
        self.schema_db = schema_db

    def create_schema(self, name: str, field_names: list[str]) -> Schema:
        """
        Validate and define a new schema.

        Args:
            name (str): The schema's slug name.
            field_names (list[str]): Names of the fields the schema defines.

        Returns:
            (Schema) The created schema.

        Raises:
            InvalidSchemaError: if the name or fields fail validation.
            SchemaExistsError: if a schema with this name already exists.
        """
        if not _SLUG_RE.match(name):
            raise InvalidSchemaError(
                f"Invalid schema name {name!r}: use lowercase letters, digits, "
                "hyphens, or underscores only (no spaces, slashes, or uppercase)."
            )

        for f in field_names:
            if not f or not f.strip():
                raise InvalidSchemaError("Field names must not be empty or whitespace.")
            if f in _RESERVED_FIELDS:
                raise InvalidSchemaError(
                    f"Field {f!r} is a reserved built-in field and cannot be redefined."
                )

        seen: set[str] = set()
        for f in field_names:
            if f in seen:
                raise InvalidSchemaError(f"Duplicate field name {f!r} in schema {name!r}.")
            seen.add(f)

        if self.schema_db.check_exists(name):
            raise SchemaExistsError(f"Schema {name!r} already exists.")

        schema = Schema(name=name, fields=[SchemaField(name=f) for f in field_names])
        self.schema_db.add(schema)
        return schema

    def list_schemas(self) -> list[Schema]:
        """
        List all schemas defined in the vault.

        Returns:
            (list[Schema]) All schemas, ordered by name.
        """
        return self.schema_db.list()

    def remove_schema(self, name: str) -> None:
        """
        Remove a schema.

        Args:
            name (str): The name of the schema to remove.

        Returns:
            None

        Raises:
            SchemaNotFoundError: if the schema does not exist.
            SchemaInUseError: if entities of that schema still exist.
        """
        if not self.schema_db.check_exists(name):
            raise SchemaNotFoundError(f"Schema {name!r} does not exist.")

        if self.schema_db.count_entities(name) > 0:
            raise SchemaInUseError(
                f"Schema {name!r} still has entities. Remove those entities first."
            )

        self.schema_db.remove(name)

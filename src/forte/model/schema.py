from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class SchemaField:
   name: str

@dataclass(frozen=True)
class Schema:
   name: str
   fields: list[SchemaField]


class SchemaError(Exception):
    """Base class for schema errors."""


class InvalidSchemaError(SchemaError):
    """Raised when a schema name or its fields fail validation."""


class SchemaExistsError(SchemaError):
    """Raised when adding a schema whose name is already defined."""


class SchemaNotFoundError(SchemaError):
    """Raised when operating on a schema that does not exist."""


class SchemaInUseError(SchemaError):
    """Raised when removing a schema that still has entities."""

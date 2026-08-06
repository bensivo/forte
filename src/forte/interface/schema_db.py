from abc import ABC, abstractmethod

from forte.model.schema import Schema


class ISchemaDb(ABC):
    """
    Interface for persisting and querying schemas. Implementations handle
    storage of schema definitions and provide the entity counts needed to
    enforce in-use guards.
    """

    @abstractmethod
    def check_exists(self, name: str) -> bool:
        """
        Check whether a schema with the given name is already defined.

        Args:
            name (str): The schema name to look up.

        Returns:
            (bool) True if a schema with this name exists.
        """
        pass

    @abstractmethod
    def add(self, schema: Schema) -> None:
        """
        Persist a new schema.

        Args:
            schema (Schema): The schema to store.

        Returns:
            None
        """
        pass

    @abstractmethod
    def get(self, name: str) -> Schema | None:
        """
        Return a single schema by name.

        Args:
            name (str): The schema name to look up.

        Returns:
            (Schema | None) The schema, or None if it does not exist.
        """
        pass

    @abstractmethod
    def list(self) -> list[Schema]:
        """
        Return all defined schemas, ordered by name.

        Returns:
            (list[Schema]) All schemas.
        """
        pass

    @abstractmethod
    def remove(self, name: str) -> None:
        """
        Delete a schema by name.

        Args:
            name (str): The schema name to remove.

        Returns:
            None
        """
        pass

    @abstractmethod
    def count_entities(self, name: str) -> int:
        """
        Count how many entities currently use the given schema.

        Args:
            name (str): The schema name to check.

        Returns:
            (int) The number of entities using this schema.
        """
        pass

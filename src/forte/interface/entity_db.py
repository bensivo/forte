from abc import ABC, abstractmethod

from forte.model.entity import Entity


class IEntityDb(ABC):
    """
    Interface for persisting and querying entities. Implementations handle
    storage of entity records (name, aliases, schema fields, and any other
    representation the storage backend keeps in sync).
    """

    @abstractmethod
    def add(self, entity: Entity) -> Entity:
        """
        Persist a new entity.

        Args:
            entity (Entity): The entity to store (without an id).

        Returns:
            (Entity) The stored entity, with its assigned ``id`` (and any
                other backend-assigned fields, e.g. ``file_path``) populated.
        """
        pass

    @abstractmethod
    def get(self, entity_id: int) -> Entity | None:
        """
        Return a single entity by id.

        Args:
            entity_id (int): The entity id to look up.

        Returns:
            (Entity | None) The entity, or None if it does not exist.
        """
        pass

    @abstractmethod
    def list(self, schema: str | None = None) -> list[Entity]:
        """
        Return all entities, or only those of a given schema, ordered by id.

        Args:
            schema (str | None): If given, only entities of this schema are
                returned.

        Returns:
            (list[Entity]) The matching entities, ordered by id.
        """
        pass

    @abstractmethod
    def update(self, entity: Entity) -> None:
        """
        Persist changes to an existing entity.

        Args:
            entity (Entity): The entity to update, with its ``id`` set.

        Returns:
            None
        """
        pass

    @abstractmethod
    def remove(self, entity_id: int) -> None:
        """
        Delete an entity by id.

        Args:
            entity_id (int): The entity id to remove.

        Returns:
            None
        """
        pass

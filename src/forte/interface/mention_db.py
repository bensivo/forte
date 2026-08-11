from abc import ABC, abstractmethod

from forte.model.mention import Mention


class IMentionDb(ABC):
    """
    Interface for persisting and querying mentions (doc-entity link rows).
    Implementations handle storage of the ``mentions`` relation only; they
    are not responsible for validating that the referenced doc/entity ids
    exist.
    """

    @abstractmethod
    def exists(self, doc_id: int, entity_id: int) -> bool:
        """
        Check whether a mention row exists for the given pair.

        Args:
            doc_id (int): The document id.
            entity_id (int): The entity id.

        Returns:
            (bool) True if a mention row exists for this doc/entity pair.
        """
        pass

    @abstractmethod
    def add(self, doc_id: int, entity_id: int, quote: str = "") -> None:
        """
        Persist a new mention row.

        Args:
            doc_id (int): The document id.
            entity_id (int): The entity id.
            quote (str): An optional supporting quote to persist on the row.

        Returns:
            None
        """
        pass

    @abstractmethod
    def list_for_doc(self, doc_id: int) -> list[Mention]:
        """
        Return every mention row belonging to a document.

        Args:
            doc_id (int): The document id whose mentions to read.

        Returns:
            (list[Mention]) The document's mentions, ordered by entity id.
        """
        pass

    @abstractmethod
    def list_for_entity(self, entity_id: int) -> list[Mention]:
        """
        Return every mention row belonging to an entity.

        Args:
            entity_id (int): The entity id whose mentions to read.

        Returns:
            (list[Mention]) The entity's mentions, ordered by doc id.
        """
        pass

    @abstractmethod
    def remove(self, doc_id: int, entity_id: int) -> None:
        """
        Delete the mention row for the given pair, if any.

        Args:
            doc_id (int): The document id.
            entity_id (int): The entity id.

        Returns:
            None
        """
        pass

    @abstractmethod
    def remove_for_doc(self, doc_id: int) -> None:
        """
        Delete all mention rows for a given document.

        Args:
            doc_id (int): The document id whose mentions should be removed.

        Returns:
            None
        """
        pass

from abc import ABC, abstractmethod
from pathlib import Path

from forte.model.document import Document


class IDocumentDb(ABC):
    """
    Interface for persisting and querying documents. Implementations handle
    storage of document records (raw/processed copies and their DB row) and
    provide the identity lookup needed to detect a no-op re-ingest.
    """

    @abstractmethod
    def find_by_identity(self, source_path: str, content_hash: str) -> Document | None:
        """
        Return the document with a matching ``source_path``/``content_hash``.

        Args:
            source_path (str): The normalized source path to look up.
            content_hash (str): The content hash to look up.

        Returns:
            (Document | None) The matching document, or None if no prior
                document matches both fields.
        """
        pass

    @abstractmethod
    def add(
        self, source_path: Path, content_hash: str, extracted_text: str, name: str
    ) -> Document:
        """
        Persist a new document: store its raw and processed copies and
        insert its row.

        Args:
            source_path (Path): The (already-normalized) source path.
            content_hash (str): The content hash of the source bytes.
            extracted_text (str): The extracted plain text to store as the
                processed copy's body.
            name (str): The document's human-readable name.

        Returns:
            (Document) The stored document, with its assigned ``id``,
                ``raw_path``, and ``processed_path`` populated.
        """
        pass

    @abstractmethod
    def add_text(self, name: str, content_hash: str, text: str) -> Document:
        """
        Persist a new document whose content originated in memory rather
        than a file on disk: store its raw and processed copies (both
        holding ``text``) and insert its row.

        Args:
            name (str): The document's human-readable name.
            content_hash (str): The content hash of ``text``.
            text (str): The document's plain-text content.

        Returns:
            (Document) The stored document, with its assigned ``id``,
                ``raw_path``, and ``processed_path`` populated.
        """
        pass

    @abstractmethod
    def list(self) -> list[Document]:
        """
        Return all documents, ordered by id.

        Returns:
            (list[Document]) All documents.
        """
        pass

    @abstractmethod
    def get(self, id: int) -> Document | None:
        """
        Return a single document by id.

        Args:
            id (int): The document id to look up.

        Returns:
            (Document | None) The document, or None if it does not exist.
        """
        pass

    @abstractmethod
    def read_processed(self, id: int) -> str | None:
        """
        Return the raw contents of a document's processed markdown copy.

        Args:
            id (int): The document id whose processed copy to read.

        Returns:
            (str | None) The processed file's full text, or None if the
                document does not exist, has no processed copy recorded, or
                that copy is missing on disk.
        """
        pass

    @abstractmethod
    def remove(self, id: int) -> None:
        """
        Delete a document, along with its raw and processed copies, by id.

        Args:
            id (int): The document id to remove.

        Returns:
            None
        """
        pass

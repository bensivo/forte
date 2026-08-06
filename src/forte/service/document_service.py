from __future__ import annotations

from pathlib import Path

from forte.interface.document_db import IDocumentDb
from forte.interface.entity_db import IEntityDb
from forte.interface.mention_db import IMentionDb
from forte.model.document import (
    Document,
    DocumentNotFoundError,
    SourceFileNotFoundError,
    compute_content_hash,
)
from forte.model.entity import EntityNotFoundError
from forte.services.text_extraction import extract_text


def _normalize_source_path(path: Path) -> str:
    """Normalize a source path consistently for identity matching.

    Always resolved to an absolute path, used both when writing
    ``source_path`` via ``add`` and when looking it up via
    ``find_by_identity``, so re-ingesting the same file (from any cwd) is
    reliably detected regardless of how the path was originally spelled.
    """
    return str(path.resolve())


class DocumentService:
    """
    Contains all the operations that can be performed on documents: ingest,
    list, show, link/unlink to entities, and remove. Documents are not
    dual-written as structured, editable knowledge like entities — each has
    exactly two on-disk artifacts (an immutable raw copy and a derived
    processed copy) plus one row in storage.

    Re-ingesting an unchanged file (same normalized source path + content
    hash) is a no-op that returns the existing document rather than erroring
    or writing a duplicate. ``link_document`` on an already-linked pair, and
    ``unlink_document`` on a not-linked pair, are also no-ops that succeed
    silently.
    """

    def __init__(self, document_db: IDocumentDb, mention_db: IMentionDb, entity_db: IEntityDb):
        """
        Args:
            document_db (IDocumentDb): Storage backend for document persistence.
            mention_db (IMentionDb): Storage backend for doc-entity mention links.
            entity_db (IEntityDb): Storage backend used to check that a
                referenced entity exists when linking/unlinking.
        """
        self.document_db = document_db
        self.mention_db = mention_db
        self.entity_db = entity_db

    def ingest_document(self, path: Path, name: str | None = None) -> Document:
        """
        Ingest a source file into the vault.

        Copies the file into raw storage, extracts its plain text into
        processed storage, and stores a document record. ``name`` is a
        human-readable label for the document; if omitted, it defaults to
        ``path``'s filename.

        If a document with the same normalized source path and content hash
        already exists, this is a no-op: the existing document is returned
        and nothing new is written — ``name`` is ignored in that case.

        Args:
            path (Path): Path to the source file to ingest.
            name (str | None): Human-readable label for the document.

        Returns:
            (Document) The ingested (or pre-existing) document.

        Raises:
            SourceFileNotFoundError: if ``path`` does not exist.
            UnsupportedFileTypeError: if the file's extension is not
                supported by :func:`forte.services.text_extraction.extract_text`
                (propagated as-is, not wrapped).
        """
        if not path.exists():
            raise SourceFileNotFoundError(f"Source file not found: {path}")

        data = path.read_bytes()
        content_hash = compute_content_hash(data)
        normalized_source_path = _normalize_source_path(path)

        # Let UnsupportedFileTypeError propagate as-is.
        extracted_text = extract_text(path)

        existing = self.document_db.find_by_identity(normalized_source_path, content_hash)
        if existing is not None:
            return existing

        doc_name = name if name else path.name
        return self.document_db.add(
            Path(normalized_source_path), content_hash, extracted_text, doc_name
        )

    def list_documents(self) -> list[Document]:
        """
        Return all documents in the vault, ordered by id.

        Returns:
            (list[Document]) All documents.
        """
        return self.document_db.list()

    def get_document(self, id: int) -> Document:
        """
        Return the document with the given id.

        Args:
            id (int): The document id to look up.

        Returns:
            (Document) The matching document.

        Raises:
            DocumentNotFoundError: if no document with that id exists.
        """
        document = self.document_db.get(id)
        if document is None:
            raise DocumentNotFoundError(f"Document #{id} does not exist.")
        return document

    def link_document(self, doc_id: int, entity_id: int, quote: str = "") -> None:
        """
        Link a document to an entity by recording a mention.

        If the pair is already linked, this is a no-op — no duplicate
        mention is created. ``quote`` is an optional supporting quote (e.g.
        cited by the agent pipeline) persisted onto the mention.

        Args:
            doc_id (int): The document id to link.
            entity_id (int): The entity id to link.
            quote (str): An optional supporting quote for the mention.

        Returns:
            None

        Raises:
            DocumentNotFoundError: if no document with ``doc_id`` exists.
            EntityNotFoundError: if no entity with ``entity_id`` exists.
        """
        if self.document_db.get(doc_id) is None:
            raise DocumentNotFoundError(f"Document #{doc_id} does not exist.")
        if self.entity_db.get(entity_id) is None:
            raise EntityNotFoundError(f"Entity #{entity_id} does not exist.")

        if self.mention_db.exists(doc_id, entity_id):
            return
        self.mention_db.add(doc_id, entity_id, quote)

    def unlink_document(self, doc_id: int, entity_id: int) -> None:
        """
        Unlink a document from an entity by removing its mention.

        If the pair is not currently linked, this is a no-op.

        Args:
            doc_id (int): The document id to unlink.
            entity_id (int): The entity id to unlink.

        Returns:
            None

        Raises:
            DocumentNotFoundError: if no document with ``doc_id`` exists.
            EntityNotFoundError: if no entity with ``entity_id`` exists.
        """
        if self.document_db.get(doc_id) is None:
            raise DocumentNotFoundError(f"Document #{doc_id} does not exist.")
        if self.entity_db.get(entity_id) is None:
            raise EntityNotFoundError(f"Entity #{entity_id} does not exist.")

        if not self.mention_db.exists(doc_id, entity_id):
            return
        self.mention_db.remove(doc_id, entity_id)

    def remove_document(self, id: int) -> None:
        """
        Remove the document with the given id.

        Cleans up all mentions referencing the document before deleting it.
        Entities themselves are never touched or deleted.

        Args:
            id (int): The document id to remove.

        Returns:
            None

        Raises:
            DocumentNotFoundError: if no document with that id exists.
        """
        if self.document_db.get(id) is None:
            raise DocumentNotFoundError(f"Document #{id} does not exist.")
        self.mention_db.remove_for_doc(id)
        self.document_db.remove(id)

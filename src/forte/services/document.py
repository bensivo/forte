"""Service layer: ingest, list, show, link, and unlink documents in a vault.

All business rules for documents live here. Documents are not dual-written as
structured, editable knowledge like entities — each has exactly two on-disk
artifacts (the immutable raw copy and the derived processed copy, both
written by :class:`DocumentRepository`) plus one row in the SQLite
``documents`` table.

Per the spec (docs/spec/forte-doc.md): re-ingesting an unchanged file (same
normalized source path + content hash) is a no-op that returns the existing
document rather than erroring or writing a duplicate. ``link_document`` on an
already-linked pair, and ``unlink_document`` on a not-linked pair, are also
no-ops that succeed silently.

The DB layer (`DocumentRepository`, `MentionRepository`, `EntityRepository`)
handles all filesystem/DB writes; the CLI layer maps the typed exceptions
raised here to Click errors.
"""

from __future__ import annotations

from pathlib import Path

from forte.db.document_repository import DocumentRepository
from forte.db.entity_repository import EntityRepository
from forte.db.mention_repository import MentionRepository
from forte.domain.document import Document, compute_content_hash
from forte.services.text_extraction import extract_text


class DocumentError(Exception):
    """Base class for document service errors."""


class DocumentNotFoundError(DocumentError):
    """Raised when operating on a document id that does not exist."""


class SourceFileNotFoundError(DocumentError):
    """Raised when the source path given to ``ingest_document`` does not exist."""


class EntityNotFoundError(DocumentError):
    """Raised when linking/unlinking references an entity id that does not exist.

    Distinct from :class:`forte.services.entity.EntityNotFoundError` (the
    entity service's own not-found error) so the document service's typed
    exceptions are all defined in one place for the CLI layer to catch by
    name; the two are otherwise semantically identical.
    """


def _normalize_source_path(path: Path) -> str:
    """Normalize a source path consistently for identity matching.

    Always resolved to an absolute path, used both when writing
    ``source_path`` via ``add`` and when looking it up via
    ``find_by_identity``, so re-ingesting the same file (from any cwd) is
    reliably detected regardless of how the path was originally spelled.
    """
    return str(path.resolve())


def ingest_document(root: Path, path: Path, name: str | None = None) -> Document:
    """Ingest a source file into the vault at ``root``.

    Copies the file into ``docs/raw/``, extracts its plain text into
    ``docs/processed/``, and inserts a ``documents`` row. Raises:
      - SourceFileNotFoundError: ``path`` does not exist.
      - UnsupportedFileTypeError: the file's extension is not supported by
        :func:`forte.services.text_extraction.extract_text` (propagated
        as-is, not wrapped).

    ``name`` is a human-readable label for the document; if omitted, it
    defaults to ``path``'s filename.

    If a document with the same normalized source path and content hash
    already exists, this is a no-op: the existing :class:`Document` is
    returned and nothing new is written (per spec) — ``name`` is ignored in
    that case.
    """
    if not path.exists():
        raise SourceFileNotFoundError(f"Source file not found: {path}")

    data = path.read_bytes()
    content_hash = compute_content_hash(data)
    normalized_source_path = _normalize_source_path(path)

    # Let UnsupportedFileTypeError propagate as-is.
    extracted_text = extract_text(path)

    repo = DocumentRepository(root)
    existing = repo.find_by_identity(normalized_source_path, content_hash)
    if existing is not None:
        return existing

    doc_name = name if name else path.name
    return repo.add(Path(normalized_source_path), content_hash, extracted_text, doc_name)


def list_documents(root: Path) -> list[Document]:
    """Return all documents in the vault, ordered by id."""
    return DocumentRepository(root).list()


def get_document(root: Path, id: int) -> Document:
    """Return the document with the given id, or raise DocumentNotFoundError."""
    document = DocumentRepository(root).get(id)
    if document is None:
        raise DocumentNotFoundError(f"Document #{id} does not exist.")
    return document


def link_document(root: Path, doc_id: int, entity_id: int, quote: str = "") -> None:
    """Link a document to an entity by inserting a ``mentions`` row.

    Raises:
      - DocumentNotFoundError: no document with ``doc_id``.
      - EntityNotFoundError: no entity with ``entity_id``.

    If the pair is already linked, this is a no-op (per spec) — no
    duplicate row is created. ``quote`` is an optional supporting quote
    (e.g. cited by the agent pipeline) persisted onto the mention row; the
    manual ``doc link`` CLI command leaves it empty, as before.
    """
    if DocumentRepository(root).get(doc_id) is None:
        raise DocumentNotFoundError(f"Document #{doc_id} does not exist.")
    if EntityRepository(root).get(entity_id) is None:
        raise EntityNotFoundError(f"Entity #{entity_id} does not exist.")

    mentions = MentionRepository(root)
    if mentions.exists(doc_id, entity_id):
        return
    mentions.add(doc_id, entity_id, quote)


def unlink_document(root: Path, doc_id: int, entity_id: int) -> None:
    """Unlink a document from an entity by removing its ``mentions`` row.

    Raises:
      - DocumentNotFoundError: no document with ``doc_id``.
      - EntityNotFoundError: no entity with ``entity_id``.

    If the pair is not currently linked, this is a no-op (per spec).
    """
    if DocumentRepository(root).get(doc_id) is None:
        raise DocumentNotFoundError(f"Document #{doc_id} does not exist.")
    if EntityRepository(root).get(entity_id) is None:
        raise EntityNotFoundError(f"Entity #{entity_id} does not exist.")

    mentions = MentionRepository(root)
    if not mentions.exists(doc_id, entity_id):
        return
    mentions.remove(doc_id, entity_id)


def remove_document(root: Path, id: int) -> None:
    """Remove the document with the given id, or raise DocumentNotFoundError.

    Cleans up all ``mentions`` rows referencing the document before deleting
    it. Entities themselves are never touched or deleted.
    """
    repo = DocumentRepository(root)
    if repo.get(id) is None:
        raise DocumentNotFoundError(f"Document #{id} does not exist.")
    MentionRepository(root).remove_for_doc(id)
    repo.remove(id)

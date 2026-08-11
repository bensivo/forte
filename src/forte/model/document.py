"""Document model.

A document is one raw source file ingested into the vault (e.g. a markdown
note, a PDF, a docx). Forte keeps a copy of the original bytes under
``docs/raw/`` and the extracted plain text under ``docs/processed/``; this
module holds the pure data record that ties those together, plus a small
content-hashing helper shared by the ingest path and future identity checks,
and the typed exceptions raised by ``DocumentService``.

Pure data — no filesystem or DB I/O happens here (beyond hashing bytes
already in memory).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


def compute_content_hash(data: bytes) -> str:
    """
    Compute a stable content hash (SHA-256, hex digest) for document bytes.

    Args:
        data (bytes): The raw document bytes to hash.

    Returns:
        (str) The hex-encoded SHA-256 digest of ``data``.
    """
    return hashlib.sha256(data).hexdigest()


@dataclass
class Document:
    """A single ingested document.

    ``name`` is a human-readable label for the document, defaulting to the
    source file's name at ingest time if not given explicitly. ``source_path``
    is the original path as given by the user at ingest time (may be absolute
    or relative to the caller's cwd — it is recorded as-is for provenance,
    not resolved against the vault). ``raw_path`` and ``processed_path`` are
    vault-relative paths under ``docs/raw/`` and ``docs/processed/``
    respectively, populated once the storage backend has written those copies
    to disk.
    """

    name: str
    source_path: str
    content_hash: str
    ingested_at: str
    status: str
    raw_path: str | None = None
    processed_path: str | None = None
    id: int | None = None


class DocumentError(Exception):
    """Base class for document errors."""


class DocumentNotFoundError(DocumentError):
    """Raised when operating on a document id that does not exist."""


class SourceFileNotFoundError(DocumentError):
    """Raised when the source path given to ``ingest_document`` does not exist."""


class UnsupportedFileTypeError(DocumentError):
    """Raised when a document's file extension has no text extractor."""


class InvalidDocumentNameError(DocumentError):
    """Raised when ``create_document`` is given an empty or whitespace-only name."""


class EmptyDocumentError(DocumentError):
    """Raised when the text returned from the editor by ``create_document`` is
    empty or whitespace-only."""


class InvalidSearchQueryError(DocumentError):
    """Raised when ``search_documents`` is given an empty/whitespace-only
    query, or a malformed regex when ``--regex`` is used."""


@dataclass
class DocumentMatch:
    """A single matching line within a document's body text.

    ``line_number`` is 1-based and counts lines of the document's BODY text
    as seen via ``forte doc show`` — not lines of the processed markdown
    file on disk, so it does not count the frontmatter block. ``spans`` are
    the ``(start, end)`` character offsets of each match within ``line``,
    letting a caller highlight the hits without re-running the search
    pattern.
    """

    line_number: int
    line: str
    spans: list[tuple[int, int]]


@dataclass
class DocumentSearchResult:
    """A document together with all of its matching lines, in the order
    the matches were found in the document's body text."""

    document: Document
    matches: list[DocumentMatch]

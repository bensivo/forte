"""Service layer: shared chunk -> embed -> store plumbing for the search index.

This module centralizes the indexing operations that both the "auto
re-embed on write" hooks and the `forte reindex` command need, so neither
has to re-derive chunking/embedding/storage logic:

- :func:`index_source` — (re)index a single doc or entity's body text.
- :func:`delete_source_index` — drop a removed source's index rows.
- :func:`reindex_vault` — rebuild the whole vault's index from scratch.
- :func:`is_stale` / :func:`ensure_fresh` — model-version staleness checks.

Only **processed doc text and entity markdown bodies** are chunked/embedded
here — frontmatter and raw source files are never read by this module.
Re-embedding failures are not swallowed: callers decide how to handle them
(e.g. log-and-skip at a write hook, or fail loudly during `forte reindex`).

Presentation-decoupled: no Click/Rich knowledge, matching the rest of the
service layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from forte.db.document_repository import DocumentRepository
from forte.db.entity_repository import EntityRepository
from forte.db.index_repository import ChunkInput, IndexRepository
from forte.domain import document_markdown, entity_markdown
from forte.services.chunking import chunk_text
from forte.services.embedding import EmbeddingClient


class StaleIndexError(Exception):
    """Raised when the search index was built with a different embedding model.

    Also raised when the index has never been built at all. Either way, the
    fix is the same: run `forte reindex` to rebuild chunks/embeddings with
    the currently-configured model.
    """


@dataclass(frozen=True)
class ReindexReport:
    """Summary counts from a full :func:`reindex_vault` run."""

    entities_indexed: int
    docs_indexed: int
    total_chunks: int


def index_source(
    root: Path,
    source_type: str,
    source_id: int,
    body_text: str,
    embedding: EmbeddingClient,
    index: IndexRepository | None = None,
) -> None:
    """(Re)index one doc or entity's body text: chunk, embed, and store.

    Chunks ``body_text`` via :func:`~forte.services.chunking.chunk_text`. If
    the body has zero chunks (empty or whitespace-only), the source's index
    rows are simply deleted — so editing a body down to nothing clears any
    stale chunks rather than leaving orphans. Otherwise every chunk is
    embedded in a single batch call and the source's chunks are atomically
    replaced via :meth:`IndexRepository.reindex_source`.

    Args:
      root: vault root.
      source_type: ``'doc'`` or ``'entity'``.
      source_id: the doc/entity integer id.
      body_text: already-extracted body text (no frontmatter).
      embedding: the embedding client to use.
      index: optional :class:`IndexRepository` to reuse (e.g. across a batch
        of sources in :func:`reindex_vault`); a default one rooted at
        ``root`` is constructed when omitted.
    """
    if index is None:
        index = IndexRepository(root)

    chunks = chunk_text(body_text)
    if not chunks:
        index.delete_source(source_type, source_id)
        return

    vectors = embedding.embed(chunks)
    chunk_inputs = [
        ChunkInput(chunk_index=i, text=text, embedding=vector)
        for i, (text, vector) in enumerate(zip(chunks, vectors))
    ]
    index.reindex_source(source_type, source_id, chunk_inputs, model=embedding.model_id)

    # Establish the vault-level index model on the first write so a normally
    # populated vault isn't treated as stale by `ensure_fresh`. We only stamp
    # when unset: an existing stamp that differs from the current model means a
    # real model change, which must stay "stale" until `forte reindex` rebuilds
    # the whole index (avoiding a mixed-model index that search would query).
    if index.get_index_model() is None:
        index.set_index_model(embedding.model_id)


def delete_source_index(
    root: Path,
    source_type: str,
    source_id: int,
    index: IndexRepository | None = None,
) -> None:
    """Drop all index rows for a removed doc/entity.

    Thin wrapper over :meth:`IndexRepository.delete_source`; a default
    :class:`IndexRepository` rooted at ``root`` is constructed when ``index``
    is omitted.
    """
    if index is None:
        index = IndexRepository(root)
    index.delete_source(source_type, source_id)


def reindex_vault(root: Path, embedding: EmbeddingClient) -> ReindexReport:
    """Rebuild the whole vault's search index from the authoritative markdown.

    Enumerates every entity (:meth:`EntityRepository.list`) and every
    document (:meth:`DocumentRepository.list`), reads each one's body text
    from disk, and re-indexes it via :func:`index_source` against a single
    shared :class:`IndexRepository`. Finally stamps the vault-level index
    model to ``embedding.model_id`` so subsequent staleness checks pass.

    Idempotent, and a clean no-op on an empty vault (the model is still
    stamped so the vault is no longer considered stale).
    """
    index = IndexRepository(root)

    entities_indexed = 0
    docs_indexed = 0
    total_chunks = 0

    for entity in EntityRepository(root).list():
        body = _read_entity_body(root, entity.file_path)
        chunks = chunk_text(body)
        index_source(
            root,
            source_type="entity",
            source_id=entity.id,
            body_text=body,
            embedding=embedding,
            index=index,
        )
        entities_indexed += 1
        total_chunks += len(chunks)

    for document in DocumentRepository(root).list():
        body = _read_document_body(root, document.processed_path)
        chunks = chunk_text(body)
        index_source(
            root,
            source_type="doc",
            source_id=document.id,
            body_text=body,
            embedding=embedding,
            index=index,
        )
        docs_indexed += 1
        total_chunks += len(chunks)

    index.set_index_model(embedding.model_id)

    return ReindexReport(
        entities_indexed=entities_indexed,
        docs_indexed=docs_indexed,
        total_chunks=total_chunks,
    )


def is_stale(
    root: Path,
    configured_model: str,
    index: IndexRepository | None = None,
) -> bool:
    """Return True if the index was never built, or was built with a different model."""
    if index is None:
        index = IndexRepository(root)
    return index.get_index_model() != configured_model


def ensure_fresh(
    root: Path,
    configured_model: str,
    index: IndexRepository | None = None,
) -> None:
    """Raise :class:`StaleIndexError` if the vault's index is stale.

    Called by the search service before running a query.
    """
    if is_stale(root, configured_model, index=index):
        raise StaleIndexError(
            "The search index was built with a different (or no) embedding "
            "model than is currently configured. Run `forte reindex` to "
            "rebuild it."
        )


def _read_entity_body(root: Path, file_path: str | None) -> str:
    """Read an entity's markdown body (free-form text, no frontmatter) from disk."""
    if not file_path:
        return ""
    text = (root / file_path).read_text(encoding="utf-8")
    return entity_markdown.from_markdown(text).body


def _read_document_body(root: Path, processed_path: str | None) -> str:
    """Read a processed document's markdown body (extracted text) from disk."""
    if not processed_path:
        return ""
    text = (root / processed_path).read_text(encoding="utf-8")
    return document_markdown.from_markdown(text).body

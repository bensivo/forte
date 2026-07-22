"""Service layer: unified semantic + keyword search over docs and entities.

This is the reusable retrieval capability behind `forte search <query>` and
the future `forte agent ask` (out of scope this pass — see
docs/impl/2026-07-21/semantic-search-tasks.md). It ties together the pieces
built by the other search tasks:

1. :func:`~forte.services.config.load_config` for the vault's configured
   embedding model.
2. :func:`~forte.services.indexing.ensure_fresh` to guard against querying a
   stale index (raises :class:`~forte.services.indexing.StaleIndexError`,
   which the CLI maps to a "run `forte reindex`" message).
3. An :class:`~forte.services.embedding.EmbeddingClient` to embed the query
   text (injectable for deterministic, free tests).
4. :func:`~forte.services.retrieval.hybrid_search` for ranked chunk hits.
5. :class:`~forte.db.entity_repository.EntityRepository` /
   :class:`~forte.db.document_repository.DocumentRepository` to resolve each
   hit's source back to a display name and on-disk link.

Presentation-decoupled: no Click/Rich here. :func:`search` returns plain
:class:`SearchResult` objects for the CLI (or any future caller) to format.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from forte.db.document_repository import DocumentRepository
from forte.db.entity_repository import EntityRepository
from forte.db.index_repository import IndexRepository
from forte.services.config import load_config
from forte.services.embedding import EmbeddingClient, SentenceTransformersEmbeddingClient
from forte.services.indexing import ensure_fresh
from forte.services.retrieval import RankedChunk, hybrid_search

#: Snippet trimming length: readable single-block preview of a matching chunk.
_SNIPPET_MAX_LEN = 200

#: Default number of results returned when the caller doesn't specify a limit.
DEFAULT_LIMIT = 10


@dataclass(frozen=True)
class SearchResult:
    """One ranked search hit, ready for a CLI (or future caller) to render.

    ``title`` and ``link`` are resolved from the hit's source: an entity's
    name and vault-relative ``file_path``, or a document's name and
    vault-relative ``processed_path``. ``snippet`` is the matching chunk text,
    trimmed to a readable length. ``score`` is the combined hybrid relevance
    score from :func:`~forte.services.retrieval.hybrid_search` — higher is
    more relevant.
    """

    source_type: str
    source_id: int
    title: str
    link: str
    snippet: str
    score: float


def search(
    root: Path,
    query: str,
    limit: int = DEFAULT_LIMIT,
    embedding: EmbeddingClient | None = None,
) -> list[SearchResult]:
    """Run a unified ranked search over the vault's indexed docs and entities.

    Loads the vault config, raises :class:`~forte.services.indexing.
    StaleIndexError` (propagated, not caught here) if the configured
    embedding model doesn't match the indexed one, embeds ``query`` with
    ``embedding`` (or a real :class:`SentenceTransformersEmbeddingClient`
    built from config when omitted), runs
    :func:`~forte.services.retrieval.hybrid_search`, and resolves each hit
    back to its source doc/entity for display.

    Hits whose source can no longer be resolved (e.g. a deleted doc/entity
    whose chunks haven't been cleaned up yet) are skipped rather than
    raising. Returns an empty list when there are no matches — not an error.

    Args:
      root: vault root.
      query: the raw user query text.
      limit: maximum number of results to return.
      embedding: optional injected embedding client (tests use the stub);
        a real client is constructed from config when omitted.
    """
    config = load_config(root)
    ensure_fresh(root, config.embedding_model)

    client = embedding or SentenceTransformersEmbeddingClient(
        model_id=config.embedding_model,
        cache_dir=root / ".forte" / "models",
    )

    query_vector = client.embed([query])[0]
    hits = hybrid_search(IndexRepository(root), query_vector, query, limit)

    entity_repo = EntityRepository(root)
    document_repo = DocumentRepository(root)

    results: list[SearchResult] = []
    for hit in hits:
        resolved = _resolve_source(hit, entity_repo, document_repo)
        if resolved is None:
            continue
        title, link = resolved
        results.append(
            SearchResult(
                source_type=hit.source_type,
                source_id=hit.source_id,
                title=title,
                link=link,
                snippet=_snippet(hit.text),
                score=hit.score,
            )
        )
    return results


def _resolve_source(
    hit: RankedChunk,
    entity_repo: EntityRepository,
    document_repo: DocumentRepository,
) -> tuple[str, str] | None:
    """Resolve a chunk hit's source to a display (title, link) pair, or None."""
    if hit.source_type == "entity":
        entity = entity_repo.get(hit.source_id)
        if entity is None or entity.file_path is None:
            return None
        return entity.name, entity.file_path
    if hit.source_type == "doc":
        document = document_repo.get(hit.source_id)
        if document is None or document.processed_path is None:
            return None
        return document.name, document.processed_path
    return None


def _snippet(text: str, max_len: int = _SNIPPET_MAX_LEN) -> str:
    """Trim chunk text to a readable single-block snippet with an ellipsis if cut."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[:max_len].rstrip() + "..."

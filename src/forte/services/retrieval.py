"""Hybrid retrieval: combine vector similarity and FTS keyword search into one
ranked list of chunk hits.

Two independent signals are computed over the index and then merged:

- **Vector side**: brute-force cosine similarity between the caller-supplied
  query embedding and every stored chunk embedding (:meth:`IndexRepository.
  all_embeddings`), ranked best-first.
- **Keyword side**: an FTS5 ``MATCH`` query (:meth:`IndexRepository.
  keyword_search`), already ranked best-first by SQLite.

Fusion of the two ranked lists into one combined score happens in exactly one
place, :func:`_reciprocal_rank_fusion`, using Reciprocal Rank Fusion (RRF) so
an exact keyword hit can surface a chunk even when its pure vector rank is
mediocre -- the "hybrid" requirement. This module is a pure function of
(query vector, query text, index reads) -> ranked hits: no Click/Rich, and no
embedding-model load -- the caller embeds the query and hands us the vector.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from forte.db.index_repository import EmbeddingRow, IndexRepository

# RRF constant: dampens the contribution of low ranks so a single top-1 hit
# doesn't overwhelm items that rank moderately well on both signals. 60 is
# the commonly cited default from the original RRF paper and works fine at
# our modest (hundreds-to-low-thousands of chunks) scale. Tune here only.
_RRF_K = 60


@dataclass(frozen=True)
class RankedChunk:
    """One chunk hit with its combined hybrid relevance score."""

    chunk_id: int
    source_type: str
    source_id: int
    text: str
    score: float


def hybrid_search(
    index: IndexRepository,
    query_vector: Sequence[float],
    query_text: str,
    limit: int = 10,
) -> list[RankedChunk]:
    """Return the top ``limit`` chunks ranked by combined vector + keyword score.

    ``query_vector`` must already be embedded by the caller (this function
    never loads an embedding model). ``query_text`` is the raw user query,
    passed through to :meth:`IndexRepository.keyword_search` for the FTS
    side. Ties in the combined score are broken by ``chunk_id`` ascending,
    for deterministic, reproducible output.
    """
    vector_ranked = _rank_by_vector_similarity(index.all_embeddings(), query_vector)
    keyword_hits = index.keyword_search(query_text)

    # Collect chunk metadata (text/source) from whichever side saw each chunk,
    # since a chunk may appear in only one of the two ranked lists.
    chunk_meta: dict[int, RankedChunk] = {}
    for row in vector_ranked:
        chunk_meta[row.chunk_id] = RankedChunk(
            chunk_id=row.chunk_id,
            source_type=row.source_type,
            source_id=row.source_id,
            text=row.text,
            score=0.0,
        )
    for hit in keyword_hits:
        chunk_meta.setdefault(
            hit.chunk_id,
            RankedChunk(
                chunk_id=hit.chunk_id,
                source_type=hit.source_type,
                source_id=hit.source_id,
                text=hit.text,
                score=0.0,
            ),
        )

    vector_order = [row.chunk_id for row in vector_ranked]
    keyword_order = [hit.chunk_id for hit in keyword_hits]
    scores = _reciprocal_rank_fusion([vector_order, keyword_order])

    ranked = [
        RankedChunk(
            chunk_id=meta.chunk_id,
            source_type=meta.source_type,
            source_id=meta.source_id,
            text=meta.text,
            score=scores.get(meta.chunk_id, 0.0),
        )
        for meta in chunk_meta.values()
    ]
    ranked.sort(key=lambda r: (-r.score, r.chunk_id))
    return ranked[:limit]


def _rank_by_vector_similarity(
    embeddings: list[EmbeddingRow], query_vector: Sequence[float]
) -> list[EmbeddingRow]:
    """Return ``embeddings`` rows sorted by cosine similarity to the query, best first.

    Both the query vector and each stored embedding are defensively
    normalized (guarding against zero-norm vectors, which are treated as
    having zero similarity to anything) so callers don't need to guarantee
    pre-normalized input.
    """
    query = np.asarray(query_vector, dtype=np.float32)
    query_norm = np.linalg.norm(query)
    if query_norm == 0.0:
        return []
    query_unit = query / query_norm

    scored = []
    for row in embeddings:
        vec = np.asarray(row.embedding, dtype=np.float32)
        vec_norm = np.linalg.norm(vec)
        if vec_norm == 0.0:
            similarity = 0.0
        else:
            similarity = float(np.dot(query_unit, vec / vec_norm))
        scored.append((similarity, row))

    scored.sort(key=lambda pair: (-pair[0], pair[1].chunk_id))
    return [row for _similarity, row in scored]


def _reciprocal_rank_fusion(ranked_lists: list[list[int]]) -> dict[int, float]:
    """Fuse multiple rank-ordered chunk-id lists into one combined score map.

    Reciprocal Rank Fusion: each list contributes ``1 / (_RRF_K + rank)`` to
    every chunk it contains, with ``rank`` starting at 1 for the best item in
    that list. A chunk appearing in more than one list accumulates a
    contribution from each -- this is what lets an exact keyword hit pull a
    chunk to the top even when its pure vector rank is lower.
    """
    scores: dict[int, float] = {}
    for ranked_list in ranked_lists:
        for rank, chunk_id in enumerate(ranked_list, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank)
    return scores

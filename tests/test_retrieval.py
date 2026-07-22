"""Integration tests for hybrid retrieval (real temp vault + IndexRepository)."""

from __future__ import annotations

from pathlib import Path

from forte.db.index_repository import ChunkInput, IndexRepository
from forte.services.init import init
from forte.services.retrieval import hybrid_search


def _vault(tmp_path: Path) -> IndexRepository:
    init(tmp_path)
    return IndexRepository(tmp_path)


def test_keyword_hit_surfaces_even_when_vector_match_is_weaker(tmp_path: Path) -> None:
    repo = _vault(tmp_path)

    # Chunk A: exact keyword match for "zeppelin", but a poor vector match.
    repo.reindex_source(
        "doc",
        1,
        [
            ChunkInput(
                chunk_index=0,
                text="zeppelin airship history",
                embedding=[0.0, 1.0, 0.0, 0.0],
            )
        ],
        model="m",
    )
    # Chunk B: no keyword overlap, but a near-perfect vector match to the query.
    repo.reindex_source(
        "doc",
        2,
        [
            ChunkInput(
                chunk_index=0,
                text="unrelated filler text",
                embedding=[1.0, 0.0, 0.0, 0.0],
            )
        ],
        model="m",
    )

    query_vector = [1.0, 0.0, 0.0, 0.0]  # matches chunk B's vector exactly
    results = hybrid_search(repo, query_vector, "zeppelin", limit=10)

    chunk_ids_in_results = [r.chunk_id for r in results]
    assert len(chunk_ids_in_results) == 2

    # The keyword hit (chunk A) must appear -- the hybrid win -- even though
    # its own vector similarity to the query is far weaker than chunk B's.
    keyword_chunk = next(r for r in results if r.text == "zeppelin airship history")
    assert keyword_chunk.chunk_id in chunk_ids_in_results
    assert keyword_chunk.source_id == 1


def test_purely_semantic_query_ranks_by_vector_similarity(tmp_path: Path) -> None:
    repo = _vault(tmp_path)

    # Neither chunk shares any keyword with the query text below.
    repo.reindex_source(
        "doc",
        1,
        [ChunkInput(chunk_index=0, text="close match content", embedding=[1.0, 0.0, 0.0, 0.0])],
        model="m",
    )
    repo.reindex_source(
        "doc",
        2,
        [ChunkInput(chunk_index=0, text="distant match content", embedding=[0.0, 1.0, 0.0, 0.0])],
        model="m",
    )

    query_vector = [0.9, 0.1, 0.0, 0.0]  # much closer to chunk 1's vector
    results = hybrid_search(repo, query_vector, "xyznonexistentquery", limit=10)

    assert len(results) == 2
    assert results[0].source_id == 1
    assert results[1].source_id == 2
    assert results[0].score > results[1].score


def test_ties_break_by_chunk_id_ascending(tmp_path: Path) -> None:
    repo = _vault(tmp_path)

    # Rank order is swapped between the two signals: chunk 1 is the best
    # vector match but the weaker keyword match, chunk 2 is the reverse.
    # By RRF symmetry (1/(k+1) + 1/(k+2) for both) the combined scores land
    # exactly equal, so ordering falls through to the chunk_id tie-break.
    repo.reindex_source(
        "doc",
        1,
        [ChunkInput(chunk_index=0, text="target term filler", embedding=[1.0, 0.0, 0.0, 0.0])],
        model="m",
    )
    repo.reindex_source(
        "doc",
        2,
        [ChunkInput(chunk_index=0, text="target term", embedding=[0.5, 0.5, 0.0, 0.0])],
        model="m",
    )

    embeddings = {row.text: row.chunk_id for row in repo.all_embeddings()}
    filler_id = embeddings["target term filler"]
    short_id = embeddings["target term"]
    assert filler_id != short_id

    query_vector = [1.0, 0.0, 0.0, 0.0]
    results = hybrid_search(repo, query_vector, "target", limit=10)

    assert len(results) == 2
    assert results[0].score == results[1].score
    expected_first = min(filler_id, short_id)
    expected_second = max(filler_id, short_id)
    assert results[0].chunk_id == expected_first
    assert results[1].chunk_id == expected_second


def test_limit_caps_number_of_results(tmp_path: Path) -> None:
    repo = _vault(tmp_path)

    for i in range(5):
        repo.reindex_source(
            "doc",
            i,
            [
                ChunkInput(
                    chunk_index=0,
                    text=f"content number {i}",
                    embedding=[1.0, 0.0, 0.0, 0.0],
                )
            ],
            model="m",
        )

    results = hybrid_search(repo, [1.0, 0.0, 0.0, 0.0], "content", limit=2)
    assert len(results) == 2

"""Integration tests for the index DB repository (real SQLite)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

from forte.db.index_repository import ChunkInput, IndexRepository
from forte.services.init import init


def _vault(tmp_path: Path) -> Path:
    init(tmp_path)
    return tmp_path


def _db_conn(tmp_path: Path) -> sqlite3.Connection:
    from forte.domain.vault import VaultLayout

    return sqlite3.connect(VaultLayout(tmp_path).db_path)


def test_reindex_source_inserts_chunks_and_fts_rows(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = IndexRepository(tmp_path)

    repo.reindex_source(
        "doc",
        1,
        [
            ChunkInput(chunk_index=0, text="hello world", embedding=[0.1, 0.2, 0.3]),
            ChunkInput(chunk_index=1, text="second chunk", embedding=[0.4, 0.5, 0.6]),
        ],
        model="stub-model",
    )

    embeddings = repo.all_embeddings()
    assert len(embeddings) == 2
    texts = {row.text for row in embeddings}
    assert texts == {"hello world", "second chunk"}
    assert all(row.source_type == "doc" and row.source_id == 1 for row in embeddings)


def test_reindex_source_replaces_old_chunks_with_no_orphans(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = IndexRepository(tmp_path)

    repo.reindex_source(
        "entity",
        7,
        [ChunkInput(chunk_index=0, text="old text alpha", embedding=[1.0, 0.0])],
        model="stub-model",
    )
    old_embeddings = repo.all_embeddings()
    assert len(old_embeddings) == 1
    old_chunk_id = old_embeddings[0].chunk_id

    repo.reindex_source(
        "entity",
        7,
        [ChunkInput(chunk_index=0, text="new text beta", embedding=[0.0, 1.0])],
        model="stub-model",
    )

    embeddings = repo.all_embeddings()
    assert len(embeddings) == 1
    assert embeddings[0].text == "new text beta"
    assert embeddings[0].chunk_id != old_chunk_id

    conn = _db_conn(tmp_path)
    try:
        chunk_rows = conn.execute("SELECT id, text FROM chunks").fetchall()
        assert len(chunk_rows) == 1
        assert chunk_rows[0][1] == "new text beta"

        fts_rows = conn.execute("SELECT chunk_id, text FROM chunks_fts").fetchall()
        assert len(fts_rows) == 1
        assert fts_rows[0][0] == embeddings[0].chunk_id

        orphan = conn.execute(
            "SELECT 1 FROM chunks_fts WHERE chunk_id = ?", (old_chunk_id,)
        ).fetchone()
        assert orphan is None
    finally:
        conn.close()


def test_reindex_source_does_not_affect_other_sources(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = IndexRepository(tmp_path)

    repo.reindex_source(
        "doc", 1, [ChunkInput(chunk_index=0, text="doc one", embedding=[1.0])], model="m"
    )
    repo.reindex_source(
        "doc", 2, [ChunkInput(chunk_index=0, text="doc two", embedding=[1.0])], model="m"
    )

    repo.reindex_source(
        "doc", 1, [ChunkInput(chunk_index=0, text="doc one updated", embedding=[1.0])], model="m"
    )

    embeddings = {row.source_id: row.text for row in repo.all_embeddings()}
    assert embeddings == {1: "doc one updated", 2: "doc two"}


def test_delete_source_removes_chunks_and_fts_rows(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = IndexRepository(tmp_path)

    repo.reindex_source(
        "doc", 1, [ChunkInput(chunk_index=0, text="keep me", embedding=[1.0])], model="m"
    )
    repo.reindex_source(
        "doc", 2, [ChunkInput(chunk_index=0, text="delete me", embedding=[1.0])], model="m"
    )

    repo.delete_source("doc", 2)

    embeddings = repo.all_embeddings()
    assert len(embeddings) == 1
    assert embeddings[0].text == "keep me"

    conn = _db_conn(tmp_path)
    try:
        remaining_fts = conn.execute("SELECT text FROM chunks_fts").fetchall()
        assert remaining_fts == [("keep me",)]
    finally:
        conn.close()


def test_delete_source_on_nonexistent_source_does_not_raise(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = IndexRepository(tmp_path)

    repo.delete_source("doc", 999)  # should not raise
    assert repo.all_embeddings() == []


def test_all_embeddings_round_trips_vector_within_float32_tolerance(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = IndexRepository(tmp_path)

    original = [0.1, -0.25, 3.14159, 0.0, -1.0]
    repo.reindex_source(
        "entity",
        5,
        [ChunkInput(chunk_index=0, text="vector test", embedding=original)],
        model="m",
    )

    rows = repo.all_embeddings()
    assert len(rows) == 1
    np.testing.assert_allclose(
        rows[0].embedding, np.asarray(original, dtype=np.float32), rtol=1e-6, atol=1e-6
    )


def test_keyword_search_matches_expected_chunk_and_not_others(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = IndexRepository(tmp_path)

    repo.reindex_source(
        "doc",
        1,
        [ChunkInput(chunk_index=0, text="the quick brown fox", embedding=[1.0])],
        model="m",
    )
    repo.reindex_source(
        "doc",
        2,
        [ChunkInput(chunk_index=0, text="a lazy dog sleeps", embedding=[1.0])],
        model="m",
    )

    hits = repo.keyword_search("fox")
    assert len(hits) == 1
    assert hits[0].source_id == 1
    assert hits[0].text == "the quick brown fox"

    no_hits = repo.keyword_search("nonexistentword")
    assert no_hits == []


def test_keyword_search_with_punctuation_does_not_crash(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = IndexRepository(tmp_path)

    repo.reindex_source(
        "doc",
        1,
        [ChunkInput(chunk_index=0, text="hello world", embedding=[1.0])],
        model="m",
    )

    hits = repo.keyword_search('foo "bar (baz) AND NOT -\'quux\'')
    assert hits == []

    hits2 = repo.keyword_search("hello!")
    # punctuation-adjacent term should not match "hello" literally, but must not crash
    assert isinstance(hits2, list)


def test_keyword_search_respects_limit(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = IndexRepository(tmp_path)

    for i in range(5):
        repo.reindex_source(
            "doc",
            i,
            [ChunkInput(chunk_index=0, text="shared keyword term", embedding=[1.0])],
            model="m",
        )

    hits = repo.keyword_search("keyword", limit=2)
    assert len(hits) == 2


def test_get_chunk_source_returns_owning_source(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = IndexRepository(tmp_path)

    repo.reindex_source(
        "entity", 42, [ChunkInput(chunk_index=0, text="owned chunk", embedding=[1.0])], model="m"
    )
    chunk_id = repo.all_embeddings()[0].chunk_id

    source = repo.get_chunk_source(chunk_id)
    assert source is not None
    assert source.source_type == "entity"
    assert source.source_id == 42

    assert repo.get_chunk_source(99999) is None


def test_get_index_model_returns_none_then_set_value(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = IndexRepository(tmp_path)

    assert repo.get_index_model() is None

    repo.set_index_model("sentence-transformers/all-MiniLM-L6-v2")
    assert repo.get_index_model() == "sentence-transformers/all-MiniLM-L6-v2"

    repo.set_index_model("sentence-transformers/all-mpnet-base-v2")
    assert repo.get_index_model() == "sentence-transformers/all-mpnet-base-v2"

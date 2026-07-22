"""Integration tests for the shared indexing service.

Uses :class:`~forte.services.embedding.StubEmbeddingClient` throughout — no
real model load happens anywhere in this suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forte.db.entity_repository import EntityRepository
from forte.db.index_repository import IndexRepository
from forte.db.schema_repository import SchemaRepository
from forte.domain.schema import Schema
from forte.services.document import ingest_document
from forte.services.embedding import StubEmbeddingClient
from forte.services.entity import add_entity
from forte.services.indexing import (
    ReindexReport,
    StaleIndexError,
    ensure_fresh,
    index_source,
    is_stale,
    reindex_vault,
)
from forte.services.init import init


def _vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    root.mkdir()
    init(root)
    return root


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


# --- index_source -------------------------------------------------------------


def test_index_source_stores_expected_chunk_count(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    index = IndexRepository(root)
    embedding = StubEmbeddingClient()

    body = "\n\n".join(f"Paragraph {i} " + ("x" * 900) for i in range(3))

    index_source(root, "entity", 1, body, embedding, index=index)

    rows = [r for r in index.all_embeddings() if r.source_type == "entity" and r.source_id == 1]
    assert len(rows) == 3
    assert [r.chunk_id for r in rows] == sorted(r.chunk_id for r in rows)


def test_index_source_replaces_chunks_on_shorter_body(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    index = IndexRepository(root)
    embedding = StubEmbeddingClient()

    long_body = "\n\n".join(f"Paragraph {i} " + ("x" * 900) for i in range(3))
    index_source(root, "entity", 1, long_body, embedding, index=index)
    assert len(index.all_embeddings()) == 3

    short_body = "Just one short paragraph."
    index_source(root, "entity", 1, short_body, embedding, index=index)

    rows = index.all_embeddings()
    assert len(rows) == 1
    assert rows[0].text == short_body


def test_index_source_empty_body_clears_chunks(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    index = IndexRepository(root)
    embedding = StubEmbeddingClient()

    index_source(root, "entity", 1, "Some content here.", embedding, index=index)
    assert len(index.all_embeddings()) == 1

    index_source(root, "entity", 1, "   \n\n  ", embedding, index=index)

    assert index.all_embeddings() == []


def test_index_source_constructs_default_repository_when_omitted(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    embedding = StubEmbeddingClient()

    index_source(root, "entity", 1, "Some content here.", embedding)

    rows = IndexRepository(root).all_embeddings()
    assert len(rows) == 1


# --- reindex_vault --------------------------------------------------------------


def _seed_vault(root: Path) -> tuple[int, int]:
    """Add one entity (with a body) and one document; return (entity_id, doc_id)."""
    SchemaRepository(root).add(Schema(name="person", fields=["role"]))
    entity = add_entity(root, "person", "Ben", field_values={"role": "Engineer"})

    # add_entity doesn't accept a body; write one via the repository directly,
    # matching how the rest of the suite bootstraps entity bodies.
    repo = EntityRepository(root)
    stored = repo.get(entity.id)
    stored.body = "Ben is an engineer who works on the Forte project."
    repo.update(stored)

    src = root.parent / "kickoff.md"
    _write(src, "Kickoff meeting notes: discussed the roadmap and next steps.")
    doc = ingest_document(root, src)

    return entity.id, doc.id


def test_reindex_vault_indexes_entities_and_docs(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    entity_id, doc_id = _seed_vault(root)

    embedding = StubEmbeddingClient(model_id="stub-v1")
    report = reindex_vault(root, embedding)

    index = IndexRepository(root)
    rows = index.all_embeddings()
    entity_rows = [r for r in rows if r.source_type == "entity" and r.source_id == entity_id]
    doc_rows = [r for r in rows if r.source_type == "doc" and r.source_id == doc_id]

    assert entity_rows, "expected chunks for the seeded entity"
    assert doc_rows, "expected chunks for the seeded document"

    assert report.entities_indexed == 1
    assert report.docs_indexed == 1
    assert report.total_chunks == len(rows)

    assert index.get_index_model() == "stub-v1"


def test_reindex_vault_empty_vault_is_clean_noop(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    embedding = StubEmbeddingClient(model_id="stub-v1")

    report = reindex_vault(root, embedding)

    assert report == ReindexReport(entities_indexed=0, docs_indexed=0, total_chunks=0)
    assert IndexRepository(root).all_embeddings() == []
    assert IndexRepository(root).get_index_model() == "stub-v1"


def test_reindex_vault_is_idempotent(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    _seed_vault(root)
    embedding = StubEmbeddingClient(model_id="stub-v1")

    first = reindex_vault(root, embedding)
    second = reindex_vault(root, embedding)

    assert first == second
    # No orphaned/duplicated chunks from running twice.
    index = IndexRepository(root)
    assert len(index.all_embeddings()) == first.total_chunks


# --- is_stale / ensure_fresh ----------------------------------------------------


def test_fresh_after_reindex_with_same_model(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    _seed_vault(root)
    embedding = StubEmbeddingClient(model_id="stub-v1")
    reindex_vault(root, embedding)

    assert is_stale(root, "stub-v1") is False
    ensure_fresh(root, "stub-v1")  # does not raise


def test_stale_when_configured_model_differs(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    _seed_vault(root)
    embedding = StubEmbeddingClient(model_id="stub-v1")
    reindex_vault(root, embedding)

    assert is_stale(root, "stub-v2") is True
    with pytest.raises(StaleIndexError):
        ensure_fresh(root, "stub-v2")


def test_stale_when_index_never_built(tmp_path: Path) -> None:
    root = _vault(tmp_path)

    assert is_stale(root, "stub-v1") is True
    with pytest.raises(StaleIndexError):
        ensure_fresh(root, "stub-v1")

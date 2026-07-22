"""Tests for automatic re-embedding wired into entity/document content writes.

These exercise the optional ``embedding`` seam added to the entity and document
services. They use :class:`StubEmbeddingClient` so nothing loads a real model,
and they assert the two things the task cares about most:

- Passing a stub client drives the derived search index (chunks appear for a
  written body; removals clear them; re-writing replaces stale rows).
- The DEFAULT path (no ``embedding`` arg) touches the index not at all — this
  is what keeps the large existing suite deterministic and model-free.
"""

from __future__ import annotations

from pathlib import Path

from forte.db.index_repository import ChunkInput, IndexRepository
from forte.db.schema_repository import SchemaRepository
from forte.domain.schema import Schema
from forte.services.document import get_document, ingest_document, remove_document
from forte.services.embedding import DEFAULT_DIMENSION, StubEmbeddingClient
from forte.services.entity import add_entity, edit_entity, remove_entity
from forte.services.init import init


def _vault(tmp_path: Path, *schemas: Schema) -> Path:
    root = tmp_path / "vault"
    root.mkdir()
    init(root)
    schema_repo = SchemaRepository(root)
    for schema in schemas:
        schema_repo.add(schema)
    return root


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _seed_entity_chunks(root: Path, entity_id: int) -> None:
    """Pretend the entity once had a body indexed, to test replace/clear paths."""
    IndexRepository(root).reindex_source(
        "entity",
        entity_id,
        [ChunkInput(chunk_index=0, text="old body text", embedding=[0.0] * DEFAULT_DIMENSION)],
        model="stub-embedding-model",
    )


class _BoomEmbeddingClient:
    """Embedding client whose :meth:`embed` always fails, to test best-effort."""

    model_id = "boom-model"
    dimension = DEFAULT_DIMENSION

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("model load failed")


# --- documents: positive indexing --------------------------------------------


def test_ingest_document_with_client_indexes_body(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    src = _write(tmp_path / "kickoff.md", "Ben works at Acme on rockets.")

    doc = ingest_document(root, src, embedding=StubEmbeddingClient())

    rows = IndexRepository(root).all_embeddings()
    assert rows, "expected chunks to be indexed for the ingested doc"
    assert all(r.source_type == "doc" and r.source_id == doc.id for r in rows)

    # The body is keyword-searchable too (FTS kept in sync).
    hits = IndexRepository(root).keyword_search("rockets")
    assert any(h.source_type == "doc" and h.source_id == doc.id for h in hits)


def test_ingest_document_without_client_creates_no_index_rows(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    src = _write(tmp_path / "kickoff.md", "Ben works at Acme on rockets.")

    ingest_document(root, src)

    # Default behavior: no client, no index rows, no model load attempted.
    assert IndexRepository(root).all_embeddings() == []


def test_reingest_unchanged_does_not_change_index(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    src = _write(tmp_path / "kickoff.md", "Ben works at Acme.")
    stub = StubEmbeddingClient()

    ingest_document(root, src, embedding=stub)
    before = len(IndexRepository(root).all_embeddings())

    # Re-ingesting an unchanged file is a no-op; it must not re-embed.
    ingest_document(root, src, embedding=stub)
    after = len(IndexRepository(root).all_embeddings())

    assert before == after and before > 0


def test_remove_document_clears_index(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    src = _write(tmp_path / "kickoff.md", "Ben works at Acme on rockets.")
    doc = ingest_document(root, src, embedding=StubEmbeddingClient())
    assert IndexRepository(root).all_embeddings()

    remove_document(root, doc.id)

    assert IndexRepository(root).all_embeddings() == []


def test_remove_document_clears_index_even_without_client(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    src = _write(tmp_path / "kickoff.md", "Ben works at Acme on rockets.")
    doc = ingest_document(root, src, embedding=StubEmbeddingClient())
    assert IndexRepository(root).all_embeddings()

    # delete_source needs no model, so it runs regardless of a client.
    remove_document(root, doc.id)

    assert IndexRepository(root).all_embeddings() == []


def test_ingest_document_reembed_failure_does_not_break_write(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    src = _write(tmp_path / "kickoff.md", "Ben works at Acme.")

    # A failing embedding client must not break the primary raw/processed/DB write.
    doc = ingest_document(root, src, embedding=_BoomEmbeddingClient())

    assert doc.id is not None
    assert get_document(root, doc.id).id == doc.id
    # The (best-effort) re-embed was swallowed, leaving the index empty.
    assert IndexRepository(root).all_embeddings() == []


# --- entities: index wiring --------------------------------------------------
#
# Note: the entity service does not (yet) accept or persist a body — both
# add_entity and edit_entity write an empty body, so a real body never reaches
# the index through them today. These tests therefore assert the *wiring*: the
# hook fires on write (replacing/clearing stale rows) and is a strict no-op
# without a client. Positive chunk creation is proven end-to-end via the doc
# path above, which shares the same index_source plumbing.


def test_add_entity_without_client_creates_no_index_rows(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person", fields=["role"]))

    add_entity(root, "person", "Ben")

    assert IndexRepository(root).all_embeddings() == []


def test_edit_entity_without_client_creates_no_index_rows(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person", fields=["role"]))
    entity = add_entity(root, "person", "Ben")

    edit_entity(root, entity.id, set_fields={"role": "Engineer"})

    assert IndexRepository(root).all_embeddings() == []


def test_add_entity_with_client_fires_hook_without_error(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person", fields=["role"]))

    # Empty body -> zero chunks; the hook still runs cleanly and keeps the
    # index consistent (no orphan rows).
    add_entity(root, "person", "Ben", embedding=StubEmbeddingClient())

    assert IndexRepository(root).all_embeddings() == []


def test_edit_entity_with_client_replaces_stale_index_rows(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person", fields=["role"]))
    entity = add_entity(root, "person", "Ben")
    _seed_entity_chunks(root, entity.id)
    assert IndexRepository(root).all_embeddings()

    # Re-embedding on edit replaces the source's rows; the (empty) new body
    # clears the stale chunks rather than leaving them orphaned.
    edit_entity(root, entity.id, set_fields={"role": "Engineer"}, embedding=StubEmbeddingClient())

    assert IndexRepository(root).all_embeddings() == []


def test_remove_entity_clears_index_rows(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person", fields=["role"]))
    entity = add_entity(root, "person", "Ben")
    _seed_entity_chunks(root, entity.id)
    assert IndexRepository(root).all_embeddings()

    # remove always drops the index rows, even with no client (delete is free).
    remove_entity(root, entity.id)

    assert IndexRepository(root).all_embeddings() == []

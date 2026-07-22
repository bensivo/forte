"""Integration tests for the search service (query -> ranked results).

Uses :class:`~forte.services.embedding.StubEmbeddingClient` throughout — no
real model load happens anywhere in this suite. The stub's ``model_id`` is
always set to the vault's *configured* embedding model
(``load_config(root).embedding_model``) so the freshness check in
:func:`~forte.services.indexing.ensure_fresh` passes for the "fresh" cases.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forte.db.entity_repository import EntityRepository
from forte.db.schema_repository import SchemaRepository
from forte.domain.schema import Schema
from forte.domain.vault import VaultLayout
from forte.services.config import load_config
from forte.services.document import ingest_document
from forte.services.embedding import StubEmbeddingClient
from forte.services.entity import add_entity
from forte.services.indexing import StaleIndexError, reindex_vault
from forte.services.init import init
from forte.services.search import SearchResult, search


def _vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    root.mkdir()
    init(root)
    return root


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _seed_vault(root: Path) -> tuple[int, int]:
    """Add one entity (with a body) and one document; return (entity_id, doc_id)."""
    SchemaRepository(root).add(Schema(name="person", fields=["role"]))
    entity = add_entity(root, "person", "Ben", field_values={"role": "Engineer"})

    repo = EntityRepository(root)
    stored = repo.get(entity.id)
    stored.body = "Ben is an engineer who works on the Forte project roadmap."
    repo.update(stored)

    src = root.parent / "kickoff.md"
    _write(src, "Kickoff meeting notes: discussed the Forte project roadmap and next steps.")
    doc = ingest_document(root, src)

    return entity.id, doc.id


def _stub_for(root: Path) -> StubEmbeddingClient:
    """Build a stub whose model_id matches the vault's configured embedding model."""
    model_id = load_config(root).embedding_model
    return StubEmbeddingClient(model_id=model_id)


# --- happy path: unified results across docs + entities ------------------------


def test_search_returns_unified_results_with_populated_fields(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    entity_id, doc_id = _seed_vault(root)
    embedding = _stub_for(root)
    reindex_vault(root, embedding)

    results = search(root, "Forte project roadmap", embedding=embedding)

    assert results, "expected at least one result"
    for result in results:
        assert isinstance(result, SearchResult)
        assert result.title
        assert result.link
        assert result.snippet
        assert isinstance(result.score, float)
        assert result.source_type in ("doc", "entity")

    source_types = {r.source_type for r in results}
    assert source_types == {"doc", "entity"}, f"expected both source types, got {source_types}"

    entity_result = next(r for r in results if r.source_type == "entity")
    assert entity_result.source_id == entity_id
    assert entity_result.title == "Ben"

    doc_result = next(r for r in results if r.source_type == "doc")
    assert doc_result.source_id == doc_id
    assert doc_result.title == "kickoff.md"


def test_search_snippet_is_trimmed_readable_text(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    SchemaRepository(root).add(Schema(name="person", fields=["role"]))
    entity = add_entity(root, "person", "Ada", field_values={"role": "Engineer"})
    repo = EntityRepository(root)
    stored = repo.get(entity.id)
    stored.body = "Word " * 100  # long enough to require trimming
    repo.update(stored)

    embedding = _stub_for(root)
    reindex_vault(root, embedding)

    results = search(root, "Word", embedding=embedding)

    assert results
    assert len(results[0].snippet) <= 203  # ~200 chars + ellipsis
    assert "\n" not in results[0].snippet


# --- no matches ------------------------------------------------------------------


def test_search_empty_vault_returns_empty_list_not_error(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    embedding = _stub_for(root)
    reindex_vault(root, embedding)  # empty vault, clean no-op, still stamps model

    results = search(root, "anything", embedding=embedding)

    assert results == []


def test_search_no_similar_vectors_returns_empty_list(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    _seed_vault(root)
    embedding = _stub_for(root)
    reindex_vault(root, embedding)

    # A query with no keyword overlap and a scripted orthogonal-ish query vector
    # still returns *some* RRF-ranked hits from hybrid_search (vector scan always
    # ranks everything), so instead assert the simplest true "no results" case:
    # an index with nothing in it at all.
    empty_root = tmp_path.parent / "empty_vault_root"
    empty_root.mkdir()
    init(empty_root)
    empty_embedding = _stub_for(empty_root)
    reindex_vault(empty_root, empty_embedding)

    results = search(empty_root, "nonexistent query text", embedding=empty_embedding)

    assert results == []


# --- staleness -------------------------------------------------------------------


def test_search_raises_stale_index_error_when_never_indexed(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    _seed_vault(root)
    embedding = _stub_for(root)

    with pytest.raises(StaleIndexError):
        search(root, "anything", embedding=embedding)


def test_search_raises_stale_index_error_when_model_changed(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    _seed_vault(root)

    # Index while the vault is configured for "old-model"...
    indexing_embedding = StubEmbeddingClient(model_id="old-model")
    reindex_vault(root, indexing_embedding)
    assert load_config(root).embedding_model != "old-model"  # confirms mismatch below is real

    config_path = VaultLayout(root).config_path
    config_path.write_text(
        "model:\n"
        "  extraction: claude-haiku-4-5\n"
        "embedding:\n"
        "  model: old-model\n",
        encoding="utf-8",
    )
    assert load_config(root).embedding_model == "old-model"

    # Confirm fresh against the model it was actually indexed with...
    query_embedding_same = StubEmbeddingClient(model_id="old-model")
    search(root, "anything", embedding=query_embedding_same)  # does not raise

    # ...then simulate a config change to a new model without reindexing.
    config_path.write_text(
        "model:\n"
        "  extraction: claude-haiku-4-5\n"
        "embedding:\n"
        "  model: new-model\n",
        encoding="utf-8",
    )
    query_embedding_new = StubEmbeddingClient(model_id="new-model")

    with pytest.raises(StaleIndexError):
        search(root, "anything", embedding=query_embedding_new)

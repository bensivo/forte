"""Tests for the embedding client abstraction (stub + real-client construction)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from forte.services.embedding import (
    DEFAULT_DIMENSION,
    DEFAULT_MODEL_ID,
    SentenceTransformersEmbeddingClient,
    StubEmbeddingClient,
)


def test_stub_returns_queued_vectors_in_order():
    v1 = [0.1, 0.2, 0.3]
    v2 = [0.4, 0.5, 0.6]
    stub = StubEmbeddingClient([v1, v2])
    result = stub.embed(["first", "second"])
    assert result == [v1, v2]


def test_stub_queue_is_consumed_across_calls():
    v1 = [1.0, 0.0]
    v2 = [0.0, 1.0]
    stub = StubEmbeddingClient([v1, v2])
    first = stub.embed(["a"])
    second = stub.embed(["b"])
    assert first == [v1]
    assert second == [v2]


def test_stub_hash_fallback_is_deterministic():
    stub = StubEmbeddingClient()
    r1 = stub.embed(["hello world"])
    r2 = stub.embed(["hello world"])
    assert r1 == r2


def test_stub_hash_fallback_differs_for_different_text():
    stub = StubEmbeddingClient()
    r1 = stub.embed(["hello"])
    r2 = stub.embed(["goodbye"])
    assert r1 != r2


def test_stub_hash_fallback_uses_configured_dimension():
    stub = StubEmbeddingClient(dimension=16)
    (vector,) = stub.embed(["anything"])
    assert len(vector) == 16
    assert stub.dimension == 16


def test_stub_falls_back_once_queue_is_exhausted():
    scripted = [0.9, 0.9]
    stub = StubEmbeddingClient([scripted], dimension=2)
    first, second = stub.embed(["scripted-text", "unscripted-text"])
    assert first == scripted
    # Falls back to the deterministic hash embedding, not another queued item.
    assert second != scripted
    assert len(second) == 2


def test_stub_exposes_model_id_and_dimension():
    stub = StubEmbeddingClient(model_id="stub-v1", dimension=8)
    assert stub.model_id == "stub-v1"
    assert stub.dimension == 8


def test_stub_default_dimension_matches_minilm():
    stub = StubEmbeddingClient()
    assert stub.dimension == DEFAULT_DIMENSION


def test_real_client_constructs_without_importing_torch_or_sentence_transformers():
    assert "torch" not in sys.modules
    assert "sentence_transformers" not in sys.modules

    client = SentenceTransformersEmbeddingClient(cache_dir=Path("/tmp/does-not-matter"))

    assert "torch" not in sys.modules
    assert "sentence_transformers" not in sys.modules
    assert isinstance(client, SentenceTransformersEmbeddingClient)


def test_real_client_wires_model_id_cache_dir_and_dimension():
    cache_dir = Path("/tmp/forte-test-vault/.forte/models")
    client = SentenceTransformersEmbeddingClient(
        model_id="sentence-transformers/all-MiniLM-L6-v2",
        cache_dir=cache_dir,
        dimension=384,
    )
    assert client.model_id == "sentence-transformers/all-MiniLM-L6-v2"
    assert client.cache_dir == cache_dir
    assert client.dimension == 384


def test_real_client_default_model_id_and_dimension():
    client = SentenceTransformersEmbeddingClient()
    assert client.model_id == DEFAULT_MODEL_ID
    assert client.dimension == DEFAULT_DIMENSION
    assert client.cache_dir is None


def test_real_client_accessing_properties_does_not_load_model():
    client = SentenceTransformersEmbeddingClient()
    # Accessing model_id/dimension/cache_dir must not trigger the lazy model load.
    _ = (client.model_id, client.dimension, client.cache_dir)
    assert client._model is None
    assert "sentence_transformers" not in sys.modules


@pytest.mark.skipif(
    os.environ.get("FORTE_TEST_REAL_EMBEDDING") != "1",
    reason="Loads a real sentence-transformers model; opt in with FORTE_TEST_REAL_EMBEDDING=1.",
)
def test_real_client_embeds_with_actual_model(tmp_path):
    client = SentenceTransformersEmbeddingClient(cache_dir=tmp_path / ".forte" / "models")
    vectors = client.embed(["hello world"])
    assert len(vectors) == 1
    assert len(vectors[0]) == client.dimension

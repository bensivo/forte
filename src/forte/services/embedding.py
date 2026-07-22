"""Embedding client abstraction with a stubbable batch ``embed()`` boundary.

Chunking, indexing, and search talk to the embedding model through a narrow
:class:`EmbeddingClient` protocol whose single method, ``embed()``, takes a
batch of texts and returns one vector per text, in order. This mirrors the
:class:`~forte.services.agent._llm.LLMClient` boundary: a real implementation
wraps a third-party library, and a stub returns deterministic, free vectors so
chunking/search/re-embed tests never need a real model.

:class:`SentenceTransformersEmbeddingClient` is the real implementation over
the `sentence-transformers` package. Both the package import and the model
load are deferred until the first embedding is actually needed, so importing
this module — and therefore the rest of the CLI — never pulls in `torch`.
:class:`StubEmbeddingClient` returns caller-scripted vectors, falling back to
a deterministic hash-based pseudo-embedding, for deterministic, free tests.
"""

from __future__ import annotations

import hashlib
import math
import random
import typing
from pathlib import Path

#: Model chosen by the load-test spike (docs/impl/2026-07-21/embedding-load-test.md).
DEFAULT_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"

#: Embedding width produced by DEFAULT_MODEL_ID.
DEFAULT_DIMENSION = 384


class EmbeddingClient(typing.Protocol):
    """Narrow embedding boundary: a batch of texts in, one vector per text out."""

    @property
    def model_id(self) -> str:
        """Identifier of the embedding model producing these vectors."""
        ...

    @property
    def dimension(self) -> int:
        """Length of each embedding vector this client produces."""
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts, returning one vector per input text, in order."""
        ...


class SentenceTransformersEmbeddingClient:
    """Real :class:`EmbeddingClient` over the `sentence-transformers` package.

    ``model_id`` and ``dimension`` are known up front (the dimension is a
    property of the chosen model, not something that requires loading it), so
    constructing this class and reading those properties never imports
    `sentence_transformers` or `torch`. The `sentence_transformers` import and
    the actual model load happen lazily, on the first call to :meth:`embed`.

    Model weights are cached to ``cache_dir`` when given — callers typically
    pass ``<vault_root>/.forte/models`` so the vault owns its own cache; with
    no ``cache_dir``, the library's own default cache location is used.
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        cache_dir: Path | None = None,
        dimension: int = DEFAULT_DIMENSION,
    ) -> None:
        self._model_id = model_id
        self._cache_dir = cache_dir
        self._dimension = dimension
        self._model: typing.Any = None

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def cache_dir(self) -> Path | None:
        return self._cache_dir

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        vectors = model.encode(texts, normalize_embeddings=True)
        return [[float(value) for value in vector] for vector in vectors]

    def _load_model(self) -> typing.Any:
        if self._model is None:
            # Lazy import: keeps `torch` out of the CLI's import graph until an
            # embedding is actually needed.
            from sentence_transformers import SentenceTransformer

            kwargs: dict[str, str] = {}
            if self._cache_dir is not None:
                kwargs["cache_folder"] = str(self._cache_dir)
            self._model = SentenceTransformer(self._model_id, **kwargs)
        return self._model


def _hash_embedding(text: str, dimension: int) -> list[float]:
    """Deterministic pseudo-embedding: the same text always yields the same vector."""
    seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)
    rng = random.Random(seed)
    vector = [rng.uniform(-1.0, 1.0) for _ in range(dimension)]
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


class StubEmbeddingClient:
    """Test double: returns queued vectors per text, in order, with a deterministic fallback.

    ``vectors``, if given, is a FIFO queue of pre-scripted vectors; each call
    to :meth:`embed` consumes one queued vector per input text, in order,
    across calls. Once the queue is exhausted (or if none was supplied), any
    further text falls back to a deterministic hash-based pseudo-embedding —
    the same text always produces the same fixed-``dimension`` unit-ish
    vector — so chunking/search/re-embed tests stay free and reproducible
    without scripting a vector for every input.
    """

    def __init__(
        self,
        vectors: list[list[float]] | None = None,
        *,
        model_id: str = "stub-embedding-model",
        dimension: int = DEFAULT_DIMENSION,
    ) -> None:
        self._queue = list(vectors) if vectors else []
        self._model_id = model_id
        self._dimension = dimension

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        if self._queue:
            return self._queue.pop(0)
        return _hash_embedding(text, self._dimension)

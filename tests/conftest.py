"""Shared pytest fixtures for the whole test suite.

The autouse fixture below stubs the CLI's embedding-client construction seam
(``forte.cli._build_embedding_client``, mirroring ``_build_llm_client``'s
stub-injection pattern used in tests/test_agent_cli.py) so that no test in
the main suite ever loads a real `sentence-transformers` model. Returning a
:class:`~forte.services.embedding.StubEmbeddingClient` whose ``model_id``
equals ``config.embedding_model`` keeps the index's stamped model consistent
with config, so `forte search` is "fresh" (not stale) after writes/reindex
in tests.
"""

from __future__ import annotations

import pytest

from forte.services.embedding import StubEmbeddingClient


@pytest.fixture(autouse=True)
def _stub_embedding_client(monkeypatch):
    import forte.cli

    def _fake(root, config):
        return StubEmbeddingClient(model_id=config.embedding_model)

    monkeypatch.setattr(forte.cli, "_build_embedding_client", _fake, raising=False)

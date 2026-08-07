"""Tests for the new LLM boundary: ``ILlmClient`` and ``AnthropicLlmClient``.

These never make a real network call. ``AnthropicLlmClient`` is exercised
only for construction/wiring; ``StubLlmClient`` (a test double, not
production code) drives everything shaped like a call to ``messages()``.
"""

from __future__ import annotations

import pytest

from forte.client.anthropic_llm_client import AnthropicLlmClient
from forte.interface.llm_client import ILlmClient
from forte.model.llm import LlmResponse, Usage

from tests.fake_llm_client import StubLlmClient


def test_stub_returns_queued_responses_in_order():
    stub = StubLlmClient(["first", "second"])
    r1 = stub.messages(system="s", user="u", schema={})
    r2 = stub.messages(system="s", user="u", schema={})
    assert r1.text == "first"
    assert r2.text == "second"


def test_stub_wraps_raw_string_with_zero_usage():
    stub = StubLlmClient(["{}"])
    resp = stub.messages(system="s", user="u", schema={})
    assert resp.usage == Usage.zero()


def test_stub_surfaces_supplied_usage():
    usage = Usage(input_tokens=10, output_tokens=5, cache_read_tokens=2)
    stub = StubLlmClient([LlmResponse(text="{}", usage=usage)])
    resp = stub.messages(system="s", user="u", schema={})
    assert resp.usage == usage


def test_stub_raises_scripted_exception():
    boom = RuntimeError("transport failure")
    stub = StubLlmClient([boom])
    with pytest.raises(RuntimeError, match="transport failure"):
        stub.messages(system="s", user="u", schema={})


def test_stub_raises_when_exhausted():
    stub = StubLlmClient(["only"])
    stub.messages(system="s", user="u", schema={})
    with pytest.raises(IndexError):
        stub.messages(system="s", user="u", schema={})


def test_anthropic_client_constructs_and_wires_model_and_key():
    client = AnthropicLlmClient(model="claude-haiku-4-5", api_key="sk-test", max_tokens=1024)
    assert isinstance(client, AnthropicLlmClient)
    assert isinstance(client, ILlmClient)
    assert client._model == "claude-haiku-4-5"
    assert client._max_tokens == 1024
    assert client._client is not None

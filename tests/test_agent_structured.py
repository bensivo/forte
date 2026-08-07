"""Tests for the bounded-retry structured-call helper."""

from __future__ import annotations

import json

import pytest

from forte.model.agent import StructuredCallError
from forte.model.llm import LlmResponse, Usage
from forte.service.agent._structured import MAX_RETRIES, structured_call
from tests.fake_llm_client import StubLlmClient


def _parse_color(text: str) -> str:
    """Parse text as JSON and validate ``color`` is a known enum value."""
    data = json.loads(text)
    color = data["color"]
    if color not in {"red", "green", "blue"}:
        raise ValueError(f"invalid color: {color}")
    return color


def test_success_first_try_returns_parsed_and_usage():
    usage = Usage(input_tokens=7, output_tokens=3)
    stub = StubLlmClient([LlmResponse(text='{"color": "red"}', usage=usage)])
    parsed, returned_usage = structured_call(
        stub, system="s", user="u", schema={}, parse=_parse_color
    )
    assert parsed == "red"
    assert returned_usage == usage


def test_success_after_transient_failures():
    usage = Usage(input_tokens=1, output_tokens=1)
    stub = StubLlmClient(
        [
            RuntimeError("net down"),
            RuntimeError("net down again"),
            LlmResponse(text='{"color": "blue"}', usage=usage),
        ]
    )
    parsed, returned_usage = structured_call(
        stub, system="s", user="u", schema={}, parse=_parse_color
    )
    assert parsed == "blue"
    assert returned_usage == usage


def test_malformed_json_exhausts_all_retries_then_raises():
    stub = StubLlmClient(["not json"] * MAX_RETRIES)
    with pytest.raises(StructuredCallError) as excinfo:
        structured_call(stub, system="s", user="u", schema={}, parse=_parse_color)
    assert isinstance(excinfo.value.last_error, json.JSONDecodeError)


def test_wrong_enum_is_retried_and_exhausts():
    stub = StubLlmClient(['{"color": "purple"}'] * MAX_RETRIES)
    with pytest.raises(StructuredCallError) as excinfo:
        structured_call(stub, system="s", user="u", schema={}, parse=_parse_color)
    assert isinstance(excinfo.value.last_error, ValueError)


def test_exactly_max_retries_attempts_on_total_failure():
    call_count = {"n": 0}

    def counting_parse(text: str) -> str:
        call_count["n"] += 1
        raise ValueError("always bad")

    stub = StubLlmClient(['{"color": "red"}'] * MAX_RETRIES)
    with pytest.raises(StructuredCallError):
        structured_call(stub, system="s", user="u", schema={}, parse=counting_parse)
    assert call_count["n"] == MAX_RETRIES
    assert MAX_RETRIES == 5

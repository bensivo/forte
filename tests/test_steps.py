"""Tests for the three LLM pipeline steps, all against the stub LLM boundary."""

from __future__ import annotations

import json

import pytest

from forte.domain.entity import Entity
from forte.services.llm import LLMResponse, StubLLMClient
from forte.services.pipeline_models import (
    CandidateEntity,
    FieldSetTarget,
    ProposedLink,
    ProposedNewEntity,
)
from forte.services.steps import extract_entities, extract_fields, resolve_candidate
from forte.services.structured import MAX_RETRIES, StructuredCallError
from forte.services.usage import Usage


def _resp(payload: dict, usage: Usage | None = None) -> LLMResponse:
    return LLMResponse(text=json.dumps(payload), usage=usage or Usage.zero())


# --- extract_entities ------------------------------------------------------


def test_extract_entities_returns_candidates_and_usage():
    usage = Usage(input_tokens=10, output_tokens=4)
    stub = StubLLMClient(
        [
            _resp(
                {
                    "entities": [
                        {"name": "Ada", "schema": "person", "supporting_quote": "Ada wrote it"}
                    ]
                },
                usage,
            )
        ]
    )
    candidates, returned_usage = extract_entities(
        stub, doc_text="Ada wrote it", schema_names=["person"]
    )
    assert candidates == [
        CandidateEntity(name="Ada", schema="person", supporting_quote="Ada wrote it")
    ]
    assert returned_usage == usage


def test_extract_entities_empty_extraction():
    stub = StubLLMClient([_resp({"entities": []})])
    candidates, _ = extract_entities(stub, doc_text="nothing here", schema_names=["person"])
    assert candidates == []


def test_extract_entities_drops_unknown_schema_without_retry():
    # Two candidates in a single (valid) response: the "widget"-schema one is
    # dropped post-parse. Only ONE response is scripted, so any retry would
    # raise IndexError — proving no retry happened.
    stub = StubLLMClient(
        [
            _resp(
                {
                    "entities": [
                        {"name": "Ada", "schema": "person", "supporting_quote": "q1"},
                        {"name": "Gizmo", "schema": "widget", "supporting_quote": "q2"},
                    ]
                }
            )
        ]
    )
    candidates, _ = extract_entities(stub, doc_text="doc", schema_names=["person"])
    assert candidates == [CandidateEntity(name="Ada", schema="person", supporting_quote="q1")]


def test_extract_entities_malformed_exhausts_retries():
    stub = StubLLMClient(["not json"] * MAX_RETRIES)
    with pytest.raises(StructuredCallError):
        extract_entities(stub, doc_text="doc", schema_names=["person"])


# --- resolve_candidate -----------------------------------------------------


def _candidate() -> CandidateEntity:
    return CandidateEntity(name="Ada", schema="person", supporting_quote="Ada wrote it")


def test_resolve_candidate_rule_match_llm_picks_link():
    existing = [Entity(schema="person", name="Ada Lovelace", aliases=["Ada"], id=3)]
    usage = Usage(input_tokens=5, output_tokens=2)
    stub = StubLLMClient([_resp({"entity_id": 3}, usage)])
    change, returned_usage = resolve_candidate(
        stub, candidate=_candidate(), doc_text="doc", existing_entities=existing
    )
    assert change == ProposedLink(
        entity_id=3,
        entity_name="Ada Lovelace",
        schema="person",
        candidate_name="Ada",
        supporting_quote="Ada wrote it",
    )
    assert returned_usage == usage


def test_resolve_candidate_rule_match_llm_says_none_new_entity():
    existing = [Entity(schema="person", name="Ada Lovelace", aliases=["Ada"], id=3)]
    stub = StubLLMClient([_resp({"entity_id": None})])
    change, _ = resolve_candidate(
        stub, candidate=_candidate(), doc_text="doc", existing_entities=existing
    )
    assert change == ProposedNewEntity(
        name="Ada", schema="person", supporting_quote="Ada wrote it"
    )


def test_resolve_candidate_no_rule_match_no_llm_call():
    # Empty stub: if the LLM were consulted, messages() would raise IndexError.
    stub = StubLLMClient([])
    change, usage = resolve_candidate(
        stub, candidate=_candidate(), doc_text="doc", existing_entities=[]
    )
    assert change == ProposedNewEntity(
        name="Ada", schema="person", supporting_quote="Ada wrote it"
    )
    assert usage == Usage.zero()


def test_resolve_candidate_out_of_set_id_is_retried_and_exhausts():
    existing = [Entity(schema="person", name="Ada Lovelace", aliases=["Ada"], id=3)]
    stub = StubLLMClient([_resp({"entity_id": 999})] * MAX_RETRIES)
    with pytest.raises(StructuredCallError):
        resolve_candidate(
            stub, candidate=_candidate(), doc_text="doc", existing_entities=existing
        )


# --- extract_fields --------------------------------------------------------


def _target() -> FieldSetTarget:
    return FieldSetTarget(name="Ada Lovelace", schema="person", entity_id=3)


def test_extract_fields_returns_field_set():
    usage = Usage(input_tokens=8, output_tokens=3)
    stub = StubLLMClient([_resp({"role": "Mathematician", "employer": ""}, usage)])
    field_set, returned_usage = extract_fields(
        stub,
        name="Ada Lovelace",
        schema_name="person",
        schema_field_names=["employer", "role"],
        doc_text="Ada was a mathematician",
        target=_target(),
        source_doc_id=7,
    )
    assert field_set is not None
    assert field_set.fields == {"role": "Mathematician"}
    assert field_set.source_doc_id == 7
    assert field_set.target == _target()
    assert returned_usage == usage


def test_extract_fields_nothing_extractable_returns_none():
    stub = StubLLMClient([_resp({"role": "", "employer": ""})])
    field_set, _ = extract_fields(
        stub,
        name="Ada Lovelace",
        schema_name="person",
        schema_field_names=["employer", "role"],
        doc_text="unrelated",
        target=_target(),
        source_doc_id=7,
    )
    assert field_set is None


def test_extract_fields_no_declared_fields_skips_llm():
    stub = StubLLMClient([])
    field_set, usage = extract_fields(
        stub,
        name="Ada Lovelace",
        schema_name="person",
        schema_field_names=[],
        doc_text="doc",
        target=_target(),
        source_doc_id=7,
    )
    assert field_set is None
    assert usage == Usage.zero()


def test_extract_fields_undeclared_field_is_retried_and_exhausts():
    stub = StubLLMClient([_resp({"role": "x", "bogus": "y"})] * MAX_RETRIES)
    with pytest.raises(StructuredCallError):
        extract_fields(
            stub,
            name="Ada Lovelace",
            schema_name="person",
            schema_field_names=["role"],
            doc_text="doc",
            target=_target(),
            source_doc_id=7,
        )

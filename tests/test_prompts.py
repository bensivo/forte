"""Tests for the in-source prompt templates, JSON schemas, and parse functions."""

from __future__ import annotations

import json

import pytest

from forte.domain.entity import Entity
from forte.services.agent._pipeline_models import CandidateEntity
from forte.services.agent._prompts import (
    EXTRACTION_SCHEMA,
    LINK_SCHEMA,
    build_extraction_user,
    build_field_schema,
    build_field_user,
    build_link_user,
    make_field_parser,
    make_link_parser,
    parse_extraction,
)

# --- JSON schema shape (Anthropic json_schema constraints) -----------------


def _assert_objects_constrained(schema: dict) -> None:
    """Every object in the schema tree must set additionalProperties + required."""
    if schema.get("type") == "object":
        assert schema.get("additionalProperties") is False
        assert "required" in schema
        for prop in schema.get("properties", {}).values():
            _assert_objects_constrained(prop)
    if schema.get("type") == "array":
        _assert_objects_constrained(schema["items"])


def test_extraction_schema_is_constrained():
    _assert_objects_constrained(EXTRACTION_SCHEMA)


def test_link_schema_is_constrained_and_nullable():
    _assert_objects_constrained(LINK_SCHEMA)
    assert LINK_SCHEMA["properties"]["entity_id"]["type"] == ["integer", "null"]


def test_build_field_schema_dynamic():
    schema = build_field_schema(["employer", "role"])
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"employer", "role"}
    assert schema["properties"]["employer"] == {"type": "string"}
    assert schema["properties"]["role"] == {"type": "string"}


# --- prompt builders inject data (work for any vault) ----------------------


def test_extraction_user_injects_schema_names_and_text():
    prompt = build_extraction_user("Ada wrote code.", ["person", "project"])
    assert "person" in prompt
    assert "project" in prompt
    assert "Ada wrote code." in prompt


def test_link_user_numbers_entities_with_real_ids():
    entities = [
        Entity(schema="person", name="Ada Lovelace", aliases=["Ada"], id=3),
        Entity(schema="person", name="Grace Hopper", id=8),
    ]
    candidate = CandidateEntity(name="Ada", schema="person", supporting_quote="Ada wrote it")
    prompt = build_link_user(candidate, "doc text here", entities)
    assert "id=3" in prompt
    assert "id=8" in prompt
    assert "Ada" in prompt
    assert "doc text here" in prompt


def test_field_user_injects_field_names():
    prompt = build_field_user("Ada Lovelace", "person", ["employer", "role"], "some doc")
    assert "employer" in prompt
    assert "role" in prompt
    assert "some doc" in prompt


# --- parse_extraction ------------------------------------------------------


def test_parse_extraction_valid():
    text = json.dumps(
        {
            "entities": [
                {"name": "Ada", "schema": "person", "supporting_quote": "Ada wrote it"},
                {"name": "Apollo", "schema": "project", "supporting_quote": "project Apollo"},
            ]
        }
    )
    result = parse_extraction(text)
    assert result == [
        CandidateEntity(name="Ada", schema="person", supporting_quote="Ada wrote it"),
        CandidateEntity(name="Apollo", schema="project", supporting_quote="project Apollo"),
    ]


def test_parse_extraction_empty_list_is_valid():
    assert parse_extraction(json.dumps({"entities": []})) == []


def test_parse_extraction_missing_entities_key_raises():
    with pytest.raises(Exception):
        parse_extraction(json.dumps({"other": []}))


def test_parse_extraction_missing_quote_raises():
    text = json.dumps({"entities": [{"name": "Ada", "schema": "person"}]})
    with pytest.raises(Exception):
        parse_extraction(text)


def test_parse_extraction_empty_quote_raises():
    text = json.dumps(
        {"entities": [{"name": "Ada", "schema": "person", "supporting_quote": "  "}]}
    )
    with pytest.raises(ValueError):
        parse_extraction(text)


def test_parse_extraction_wrong_type_raises():
    text = json.dumps(
        {"entities": [{"name": 5, "schema": "person", "supporting_quote": "q"}]}
    )
    with pytest.raises(ValueError):
        parse_extraction(text)


def test_parse_extraction_malformed_json_raises():
    with pytest.raises(json.JSONDecodeError):
        parse_extraction("not json")


# --- make_link_parser ------------------------------------------------------


def test_link_parser_null_is_none():
    parse = make_link_parser([3, 8])
    assert parse(json.dumps({"entity_id": None})) is None


def test_link_parser_valid_id():
    parse = make_link_parser([3, 8])
    assert parse(json.dumps({"entity_id": 3})) == 3


def test_link_parser_out_of_set_raises():
    parse = make_link_parser([3, 8])
    with pytest.raises(ValueError):
        parse(json.dumps({"entity_id": 999}))


def test_link_parser_rejects_bool():
    parse = make_link_parser([1])
    with pytest.raises(ValueError):
        parse(json.dumps({"entity_id": True}))


def test_link_parser_missing_key_raises():
    parse = make_link_parser([3])
    with pytest.raises(Exception):
        parse(json.dumps({}))


# --- make_field_parser -----------------------------------------------------


def test_field_parser_valid_subset():
    parse = make_field_parser(["employer", "role"])
    result = parse(json.dumps({"role": "Mathematician", "employer": ""}))
    assert result == {"role": "Mathematician", "employer": ""}


def test_field_parser_unknown_field_raises():
    parse = make_field_parser(["role"])
    with pytest.raises(ValueError):
        parse(json.dumps({"role": "x", "employer": "y"}))


def test_field_parser_non_string_value_raises():
    parse = make_field_parser(["role"])
    with pytest.raises(ValueError):
        parse(json.dumps({"role": 5}))

"""Tests for the rule-based, non-LLM candidate matcher."""

from forte.domain.entity import Entity
from forte.services.linking import find_candidates


def test_exact_name_match():
    entities = [Entity(id=1, schema="person", name="Ada Lovelace")]
    result = find_candidates("Ada Lovelace", "person", entities)
    assert result == [entities[0]]


def test_exact_alias_match():
    entities = [Entity(id=1, schema="person", name="Ada Lovelace", aliases=["Ada"])]
    result = find_candidates("Ada", "person", entities)
    assert result == [entities[0]]


def test_normalized_name_match_case_and_whitespace():
    entities = [Entity(id=1, schema="person", name="Ada  Lovelace")]
    result = find_candidates("ada lovelace", "person", entities)
    assert result == [entities[0]]


def test_normalized_alias_match_case_and_whitespace():
    entities = [Entity(id=1, schema="person", name="Ada Lovelace", aliases=["Countess  Lovelace"])]
    result = find_candidates("countess lovelace", "person", entities)
    assert result == [entities[0]]


def test_no_match_returns_empty_list():
    entities = [Entity(id=1, schema="person", name="Ada Lovelace")]
    result = find_candidates("Charles Babbage", "person", entities)
    assert result == []


def test_schema_scoping_same_string_different_schema_no_match():
    entities = [Entity(id=1, schema="project", name="Apollo")]
    result = find_candidates("Apollo", "person", entities)
    assert result == []


def test_deduplication_when_entity_matches_multiple_ways():
    # "Ada Lovelace" matches exactly on name, and its alias "ada lovelace"
    # would also match via normalization -- the entity should still appear
    # only once.
    entities = [
        Entity(id=1, schema="person", name="Ada Lovelace", aliases=["ada lovelace"])
    ]
    result = find_candidates("Ada Lovelace", "person", entities)
    assert result == [entities[0]]


def test_works_with_plain_list_of_entities_no_db():
    entities = [
        Entity(id=2, schema="person", name="Bob"),
        Entity(id=1, schema="person", name="Bob"),
    ]
    result = find_candidates("Bob", "person", entities)
    # Stable order by id, de-duplicated per-entity (these are distinct entities
    # sharing a name, both should match, ordered by id).
    assert [e.id for e in result] == [1, 2]

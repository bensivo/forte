"""Tests for the in-memory agent pipeline domain models."""

from __future__ import annotations

from forte.services.pipeline_models import (
    CandidateEntity,
    Decision,
    FieldSetTarget,
    ProposedFieldSet,
    ProposedLink,
    ProposedNewEntity,
    RunStage,
    RunState,
)
from forte.services.usage import Usage


def test_candidate_entity_construction() -> None:
    c = CandidateEntity(name="Alice", schema="person", supporting_quote="Alice said hi")
    assert c.name == "Alice"
    assert c.schema == "person"
    assert c.supporting_quote == "Alice said hi"


def test_proposed_new_entity_defaults_and_fields() -> None:
    p = ProposedNewEntity(name="Alice", schema="person", supporting_quote="quote")
    assert p.aliases == []
    assert p.fields == {}

    p2 = ProposedNewEntity(
        name="Bob",
        schema="person",
        supporting_quote="quote",
        aliases=["Bobby"],
        fields={"role": "engineer"},
    )
    assert p2.aliases == ["Bobby"]
    assert p2.fields == {"role": "engineer"}


def test_proposed_link_round_trips_fields() -> None:
    link = ProposedLink(
        entity_id=42,
        entity_name="Alice",
        schema="person",
        candidate_name="Alice",
        supporting_quote="Alice went to the store",
    )
    assert link.entity_id == 42
    assert link.entity_name == "Alice"
    assert link.schema == "person"
    assert link.candidate_name == "Alice"
    assert link.supporting_quote == "Alice went to the store"


def test_field_set_target_invariant_entity_id() -> None:
    t = FieldSetTarget(name="Alice", schema="person", entity_id=1)
    assert t.is_valid()
    assert t.entity_id == 1
    assert t.new_entity_ref is None


def test_field_set_target_invariant_new_entity_ref() -> None:
    t = FieldSetTarget(name="Alice", schema="person", new_entity_ref=0)
    assert t.is_valid()
    assert t.new_entity_ref == 0
    assert t.entity_id is None


def test_field_set_target_invariant_violation_both_set() -> None:
    t = FieldSetTarget(name="Alice", schema="person", entity_id=1, new_entity_ref=0)
    assert not t.is_valid()


def test_field_set_target_invariant_violation_neither_set() -> None:
    t = FieldSetTarget(name="Alice", schema="person")
    assert not t.is_valid()


def test_proposed_field_set_round_trips_fields() -> None:
    target = FieldSetTarget(name="Alice", schema="person", entity_id=7)
    pfs = ProposedFieldSet(
        target=target,
        fields={"role": "engineer", "team": "platform"},
        source_doc_id=99,
    )
    assert pfs.target.entity_id == 7
    assert pfs.fields == {"role": "engineer", "team": "platform"}
    assert pfs.source_doc_id == 99


def test_decision_wraps_proposed_change() -> None:
    change = ProposedNewEntity(name="Alice", schema="person", supporting_quote="q")
    d = Decision(change=change, approved=True)
    assert d.change is change
    assert d.approved is True


def test_run_state_defaults() -> None:
    rs = RunState(doc_id=1)
    assert rs.stage == RunStage.EXTRACTING
    assert rs.candidates == []
    assert rs.proposed_links == []
    assert rs.proposed_new_entities == []
    assert rs.proposed_field_sets == []
    assert rs.usage == Usage.zero()


def test_run_state_add_usage_accumulates() -> None:
    rs = RunState(doc_id=1)
    rs.add_usage(Usage(input_tokens=10, output_tokens=5))
    rs.add_usage(Usage(input_tokens=3, output_tokens=2, cache_read_tokens=1))

    assert rs.usage == Usage(
        input_tokens=13,
        output_tokens=7,
        cache_read_tokens=1,
        cache_creation_tokens=0,
    )


def test_run_state_stage_transitions() -> None:
    rs = RunState(doc_id=1)
    for stage in RunStage:
        rs.stage = stage
        assert rs.stage == stage

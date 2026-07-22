"""Tests for the reviewer seam (src/forte/services/review.py)."""

from forte.services.agent._pipeline_models import ProposedLink, ProposedNewEntity
from forte.services.agent._review import AutoApproveReviewer, ScriptedReviewer


def _changes():
    return [
        ProposedNewEntity(
            name="Alice",
            schema="person",
            supporting_quote="Alice said hi.",
        ),
        ProposedLink(
            entity_id=42,
            entity_name="Bob",
            schema="person",
            candidate_name="Bob",
            supporting_quote="Bob replied.",
        ),
        ProposedNewEntity(
            name="Acme Corp",
            schema="organization",
            supporting_quote="Acme Corp was mentioned.",
        ),
    ]


def test_auto_approve_reviewer_approves_everything_preserving_order():
    changes = _changes()
    decisions = AutoApproveReviewer().review(changes)

    assert len(decisions) == len(changes)
    for change, decision in zip(changes, decisions):
        assert decision.approved is True
        assert decision.change is change


def test_scripted_reviewer_with_bool_list_approves_and_rejects():
    changes = _changes()
    reviewer = ScriptedReviewer([True, False, True])

    decisions = reviewer.review(changes)

    assert [d.approved for d in decisions] == [True, False, True]
    for change, decision in zip(changes, decisions):
        assert decision.change is change


def test_scripted_reviewer_with_predicate():
    changes = _changes()
    reviewer = ScriptedReviewer(lambda c: getattr(c, "schema", None) == "person")

    decisions = reviewer.review(changes)

    assert [d.approved for d in decisions] == [True, True, False]


def test_decisions_carry_original_change_objects_for_downstream_committer():
    changes = _changes()
    decisions = AutoApproveReviewer().review(changes)

    new_entity_decision = decisions[0]
    assert new_entity_decision.change.supporting_quote == "Alice said hi."

    link_decision = decisions[1]
    assert link_decision.change.entity_id == 42
    assert link_decision.change.supporting_quote == "Bob replied."

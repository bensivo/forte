"""Tests for the interactive Click-based reviewer."""

from __future__ import annotations

from forte.cli.review_tui import InteractiveReviewer
from forte.services.pipeline_models import (
    Decision,
    FieldSetTarget,
    ProposedFieldSet,
    ProposedLink,
    ProposedNewEntity,
)


def _script(monkeypatch, answers: list[bool]) -> None:
    it = iter(answers)
    monkeypatch.setattr("click.confirm", lambda *a, **k: next(it))


def test_empty_changes_returns_empty_no_prompt(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr("click.confirm", lambda *a, **k: calls.append(1) or True)

    reviewer = InteractiveReviewer()
    result = reviewer.review([])

    assert result == []
    assert calls == []
    assert capsys.readouterr().out == ""


def test_new_entity_render_and_decision(monkeypatch, capsys):
    change = ProposedNewEntity(
        name="Alice",
        schema="person",
        supporting_quote="Alice works at Acme.",
        aliases=["Al"],
        fields={"role": "engineer"},
    )
    _script(monkeypatch, [True])

    reviewer = InteractiveReviewer()
    result = reviewer.review([change])

    assert result == [Decision(change=change, approved=True)]
    out = capsys.readouterr().out
    assert "New person entity: Alice" in out
    assert "Al" in out
    assert "role=engineer" in out
    assert 'quote: "Alice works at Acme.' in out


def test_link_render_and_decision(monkeypatch, capsys):
    change = ProposedLink(
        entity_id=42,
        entity_name="Alice Smith",
        schema="person",
        candidate_name="Alice",
        supporting_quote="Alice said hi.",
    )
    _script(monkeypatch, [False])

    reviewer = InteractiveReviewer()
    result = reviewer.review([change])

    assert result == [Decision(change=change, approved=False)]
    out = capsys.readouterr().out
    assert "Link 'Alice'" in out
    assert "#42" in out
    assert "Alice Smith" in out
    assert 'quote: "Alice said hi.' in out


def test_field_set_render_and_decision(monkeypatch, capsys):
    target = FieldSetTarget(name="Alice", schema="person", entity_id=1)
    change = ProposedFieldSet(
        target=target,
        fields={"email": "alice@example.com", "role": "engineer"},
        source_doc_id=7,
    )
    _script(monkeypatch, [True])

    reviewer = InteractiveReviewer()
    result = reviewer.review([change])

    assert result == [Decision(change=change, approved=True)]
    out = capsys.readouterr().out
    assert "Set fields on person 'Alice'" in out
    assert "email=alice@example.com" in out
    assert "role=engineer" in out


def test_multiple_changes_in_order(monkeypatch, capsys):
    c1 = ProposedNewEntity(name="A", schema="person", supporting_quote="q1")
    c2 = ProposedLink(
        entity_id=1, entity_name="B", schema="person", candidate_name="B2", supporting_quote="q2"
    )
    c3 = ProposedFieldSet(
        target=FieldSetTarget(name="A", schema="person", entity_id=2),
        fields={"k": "v"},
        source_doc_id=1,
    )
    _script(monkeypatch, [True, False, True])

    reviewer = InteractiveReviewer()
    result = reviewer.review([c1, c2, c3])

    assert result == [
        Decision(change=c1, approved=True),
        Decision(change=c2, approved=False),
        Decision(change=c3, approved=True),
    ]

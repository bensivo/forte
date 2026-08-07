"""Integration tests for the best-effort commit step (agent pipeline)."""

from __future__ import annotations

from pathlib import Path

from forte.model.agent import (
    FieldSetTarget,
    ProposedFieldSet,
    ProposedLink,
    ProposedNewEntity,
)
from forte.service.agent._commit import commit_changes
from tests.agent_stack import Stack, build_stack, mentions_for_entity


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _vault_with_doc(tmp_path: Path):
    stack = build_stack(tmp_path)
    stack.schema_service.create_schema("person", ["employer", "role"])
    src = _write(tmp_path / "kickoff.md", "Ada Lovelace worked with Grace Hopper.")
    doc = stack.document_service.ingest_document(src)
    return stack, doc


def _commit(stack: Stack, doc_id: int, changes):
    return commit_changes(
        doc_id,
        changes,
        document_service=stack.document_service,
        entity_service=stack.entity_service,
    )


def test_commit_new_entity_link_and_field_set_all_land(tmp_path: Path) -> None:
    stack, doc = _vault_with_doc(tmp_path)
    existing = stack.entity_service.add_entity("person", "Grace Hopper")

    changes = [
        ProposedNewEntity(
            name="Ada Lovelace",
            schema="person",
            supporting_quote="Ada Lovelace worked with",
            aliases=["Ada"],
            fields={"role": "Mathematician"},
        ),
        ProposedLink(
            entity_id=existing.id,
            entity_name="Grace Hopper",
            schema="person",
            candidate_name="Grace Hopper",
            supporting_quote="worked with Grace Hopper",
        ),
        ProposedFieldSet(
            target=FieldSetTarget(name="Ada Lovelace", schema="person", new_entity_ref=0),
            fields={"employer": "Analytical Engines Inc."},
            source_doc_id=doc.id,
        ),
    ]

    report = _commit(stack, doc.id, changes)

    assert len(report.failures) == 0
    assert len(report.successes) == 3

    entities = stack.entity_service.list_entities(schema="person")
    names = {e.name for e in entities}
    assert "Ada Lovelace" in names
    ada = next(e for e in entities if e.name == "Ada Lovelace")
    assert ada.fields["role"] == "Mathematician"
    assert ada.fields["employer"] == "Analytical Engines Inc."

    md_files = list((stack.root / "entities" / "person").glob("*.md"))
    assert any("ada" in f.name.lower() for f in md_files)

    mentions_ada = mentions_for_entity(stack.root, ada.id)
    assert len(mentions_ada) == 1
    assert mentions_ada[0][1] == "Ada Lovelace worked with"

    mentions_grace = mentions_for_entity(stack.root, existing.id)
    assert len(mentions_grace) == 1
    assert mentions_grace[0][1] == "worked with Grace Hopper"


def test_commit_is_best_effort_partial_failure(tmp_path: Path) -> None:
    stack, doc = _vault_with_doc(tmp_path)

    changes = [
        ProposedNewEntity(
            name="Ada Lovelace",
            schema="person",
            supporting_quote="quote",
        ),
        ProposedLink(
            entity_id=99999,
            entity_name="Nonexistent",
            schema="person",
            candidate_name="Nonexistent",
            supporting_quote="quote",
        ),
    ]

    report = _commit(stack, doc.id, changes)

    assert len(report.successes) == 1
    assert len(report.failures) == 1
    failed = report.failures[0]
    assert isinstance(failed.change, ProposedLink)
    assert failed.error

    entities = stack.entity_service.list_entities(schema="person")
    assert any(e.name == "Ada Lovelace" for e in entities)


def test_commit_field_set_never_overwrites_nonempty_field(tmp_path: Path) -> None:
    stack, doc = _vault_with_doc(tmp_path)
    existing = stack.entity_service.add_entity(
        "person",
        "Ada Lovelace",
        field_values={"employer": "Analytical Engine Co.", "role": ""},
    )

    changes = [
        ProposedFieldSet(
            target=FieldSetTarget(name="Ada Lovelace", schema="person", entity_id=existing.id),
            fields={"employer": "Somewhere Else", "role": "Mathematician"},
            source_doc_id=doc.id,
        ),
    ]

    report = _commit(stack, doc.id, changes)

    assert len(report.failures) == 0
    updated = stack.entity_service.get_entity(existing.id)
    assert updated.fields["employer"] == "Analytical Engine Co."
    assert updated.fields["role"] == "Mathematician"


def test_commit_field_set_resolves_new_entity_ref(tmp_path: Path) -> None:
    stack, doc = _vault_with_doc(tmp_path)

    changes = [
        ProposedNewEntity(
            name="Grace Hopper",
            schema="person",
            supporting_quote="quote",
        ),
        ProposedFieldSet(
            target=FieldSetTarget(name="Grace Hopper", schema="person", new_entity_ref=0),
            fields={"role": "Rear Admiral"},
            source_doc_id=doc.id,
        ),
    ]

    report = _commit(stack, doc.id, changes)

    assert len(report.failures) == 0
    entities = stack.entity_service.list_entities(schema="person")
    grace = next(e for e in entities if e.name == "Grace Hopper")
    assert grace.fields["role"] == "Rear Admiral"

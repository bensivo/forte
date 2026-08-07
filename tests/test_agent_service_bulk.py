"""Integration tests for AgentService.process_document_bulk.

All tests run against a temp vault with real SQLite/markdown, a stubbed LLM
boundary (:class:`StubLlmClient`), and a scripted :class:`EditorSession` whose
``edit`` is a plain ``str -> str`` function. No real editor is ever spawned.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from forte.model.agent import EditorAbortedError
from forte.model.config import Config
from forte.model.llm import LlmResponse, Usage
from forte.service.agent_service import AgentService
from tests.agent_stack import Stack, build_stack, mentions_for_doc, mentions_for_entity
from tests.fake_llm_client import StubLlmClient

# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


class FakeConfigService:
    """Stands in for ConfigService: reports a fixed extraction model."""

    def get_config(self):
        return Config(
            extraction_model="claude-haiku-4-5", anthropic_api_key="sk-test", editor=None
        )


def _agent(stack: Stack, llm) -> AgentService:
    return AgentService(
        llm,
        FakeConfigService(),
        stack.document_service,
        stack.entity_service,
        stack.schema_service,
    )


def _vault_with_doc(tmp_path: Path, *, fields: list[str], text: str):
    stack = build_stack(tmp_path)
    stack.schema_service.create_schema("person", fields)
    src = tmp_path / "kickoff.md"
    src.write_text(text, encoding="utf-8")
    doc = stack.document_service.ingest_document(src)
    return stack, doc


def _resp(payload: dict, usage: Usage | None = None) -> LlmResponse:
    return LlmResponse(text=json.dumps(payload), usage=usage or Usage.zero())


def _extract(*names: str, usage: Usage | None = None) -> LlmResponse:
    """An extract-entities response proposing a person candidate per name."""
    return _resp(
        {
            "entities": [
                {
                    "name": name,
                    "schema": "person",
                    "supporting_quote": f"{name} did a thing.",
                }
                for name in names
            ]
        },
        usage,
    )


_LINE_RE = re.compile(r"^(?P<indent>\s*)\[(?P<action>[^\]]*)\]\s+(?P<cid>\S+)(?P<rest>.*)$")


class ScriptedEditor:
    """EditorSession stub: applies a scripted ``str -> str`` transform.

    Records the text it received so tests can assert on what was rendered.
    """

    def __init__(self, transform):
        self._transform = transform
        self.received: str | None = None
        self.calls = 0

    def edit(self, text: str) -> str:
        self.received = text
        self.calls += 1
        return self._transform(text)


def unchanged(text: str) -> str:
    return text


def flip_to_no(*change_ids: str):
    """Transform: flip the given change-ids' action tokens to ``[n]``."""
    targets = set(change_ids)

    def _transform(text: str) -> str:
        out = []
        for line in text.splitlines():
            m = _LINE_RE.match(line)
            if m and m.group("cid") in targets:
                out.append(f"{m.group('indent')}[n] {m.group('cid')}{m.group('rest')}")
            else:
                out.append(line)
        return "\n".join(out)

    return _transform


def delete_lines(*change_ids: str):
    """Transform: delete the proposal lines for the given change-ids entirely."""
    targets = set(change_ids)

    def _transform(text: str) -> str:
        out = []
        for line in text.splitlines():
            m = _LINE_RE.match(line)
            if m and m.group("cid") in targets:
                continue
            out.append(line)
        return "\n".join(out)

    return _transform


def rename(old_name: str, new_name: str):
    """Transform: edit a new-entity line's name from ``old_name`` to ``new_name``."""

    def _transform(text: str) -> str:
        return text.replace(f"entity: {old_name}", f"entity: {new_name}")

    return _transform


def combine(*transforms):
    """Chain several transforms left-to-right."""

    def _transform(text: str) -> str:
        for t in transforms:
            text = t(text)
        return text

    return _transform


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_all_approved_commits_everything(tmp_path: Path) -> None:
    stack, doc = _vault_with_doc(
        tmp_path, fields=["role", "employer"], text="Ada Lovelace wrote the first algorithm."
    )
    stub = StubLlmClient(
        [
            _extract("Ada Lovelace"),
            _resp({"role": "Mathematician", "employer": ""}),
        ]
    )
    editor = ScriptedEditor(unchanged)

    result = _agent(stack, stub).process_document_bulk(doc.id, editor=editor, dry_run=False)

    assert editor.calls == 1
    # editor received a three-section document containing the proposal
    assert "## New entities" in editor.received
    assert "## Field updates" in editor.received
    assert result.commit_report is not None
    assert len(result.commit_report.failures) == 0

    entities = stack.entity_service.list_entities(schema="person")
    ada = next(e for e in entities if e.name == "Ada Lovelace")
    assert ada.fields["role"] == "Mathematician"
    assert len(mentions_for_entity(stack.root, ada.id)) == 1


def test_mixed_approve_and_skip(tmp_path: Path) -> None:
    stack, doc = _vault_with_doc(
        tmp_path, fields=["role", "employer"], text="Ada Lovelace and Charles Babbage."
    )
    stub = StubLlmClient(
        [
            _extract("Ada Lovelace", "Charles Babbage"),
            # field-extract EVERY new entity (both), in all_new order
            _resp({"role": "Mathematician", "employer": ""}),  # Ada (c2)
            _resp({"role": "Engineer", "employer": ""}),  # Babbage (c3)
        ]
    )
    # all_changes: [Ada c0, Babbage c1, fieldAda c2, fieldBabbage c3]
    # skip Babbage entirely: reject the entity AND its field-set.
    editor = ScriptedEditor(flip_to_no("c1", "c3"))

    result = _agent(stack, stub).process_document_bulk(doc.id, editor=editor, dry_run=False)

    assert result.commit_report is not None
    assert len(result.commit_report.failures) == 0

    entities = stack.entity_service.list_entities(schema="person")
    names = {e.name for e in entities}
    assert "Ada Lovelace" in names
    assert "Charles Babbage" not in names
    ada = next(e for e in entities if e.name == "Ada Lovelace")
    assert ada.fields["role"] == "Mathematician"


def test_deleted_line_is_treated_as_skip(tmp_path: Path) -> None:
    stack, doc = _vault_with_doc(
        tmp_path, fields=["role", "employer"], text="Ada Lovelace and Charles Babbage."
    )
    stub = StubLlmClient(
        [
            _extract("Ada Lovelace", "Charles Babbage"),
            _resp({"role": "Mathematician", "employer": ""}),
            _resp({"role": "Engineer", "employer": ""}),
        ]
    )
    # Delete Babbage's entity line AND its field line -> both skipped.
    editor = ScriptedEditor(delete_lines("c1", "c3"))

    result = _agent(stack, stub).process_document_bulk(doc.id, editor=editor, dry_run=False)

    assert result.commit_report is not None
    entities = stack.entity_service.list_entities(schema="person")
    names = {e.name for e in entities}
    assert names == {"Ada Lovelace"}


def test_promote_rejected_entity_when_field_set_approved(tmp_path: Path) -> None:
    """Edge case: reject a NEW entity but approve its field-set -> entity created."""
    stack, doc = _vault_with_doc(
        tmp_path, fields=["role", "employer"], text="Ada Lovelace wrote the first algorithm."
    )
    stub = StubLlmClient(
        [
            _extract("Ada Lovelace"),
            _resp({"role": "Mathematician", "employer": ""}),
        ]
    )
    # all_changes: [Ada c0, fieldAda c1]. Reject the entity, keep the field-set.
    editor = ScriptedEditor(flip_to_no("c0"))

    result = _agent(stack, stub).process_document_bulk(doc.id, editor=editor, dry_run=False)

    assert result.commit_report is not None
    assert len(result.commit_report.failures) == 0

    entities = stack.entity_service.list_entities(schema="person")
    # The entity was promoted back in and created...
    ada = next(e for e in entities if e.name == "Ada Lovelace")
    # ...and its field-set landed on it (new_entity_ref realigned correctly).
    assert ada.fields["role"] == "Mathematician"
    assert len(mentions_for_entity(stack.root, ada.id)) == 1


def test_promote_keeps_new_entity_ref_aligned_with_other_survivors(tmp_path: Path) -> None:
    """A rejected+promoted entity must not misalign a surviving entity's field-set.

    all_new = [Ada(0), Babbage(1)]. Reject Ada's entity line (c0) but approve
    its field-set (c2) -> Ada is promoted. Babbage (c1) and its field-set (c3)
    are approved normally. After promotion Ada stays at index 0 and Babbage at
    index 1, so both field-sets must land on the RIGHT entity.
    """
    stack, doc = _vault_with_doc(
        tmp_path, fields=["role", "employer"], text="Ada Lovelace and Charles Babbage."
    )
    stub = StubLlmClient(
        [
            _extract("Ada Lovelace", "Charles Babbage"),
            _resp({"role": "Mathematician", "employer": ""}),  # Ada c2
            _resp({"role": "Engineer", "employer": ""}),  # Babbage c3
        ]
    )
    # Reject Ada's entity line only; everything else stays [y].
    editor = ScriptedEditor(flip_to_no("c0"))

    result = _agent(stack, stub).process_document_bulk(doc.id, editor=editor, dry_run=False)

    assert result.commit_report is not None
    assert len(result.commit_report.failures) == 0

    entities = stack.entity_service.list_entities(schema="person")
    by_name = {e.name: e for e in entities}
    assert set(by_name) == {"Ada Lovelace", "Charles Babbage"}
    assert by_name["Ada Lovelace"].fields["role"] == "Mathematician"
    assert by_name["Charles Babbage"].fields["role"] == "Engineer"


def test_link_field_set_commits_against_existing_entity(tmp_path: Path) -> None:
    stack, doc = _vault_with_doc(tmp_path, fields=["role"], text="Ada wrote the first algorithm.")
    existing = stack.entity_service.add_entity("person", "Ada Lovelace", aliases=["Ada"])
    stub = StubLlmClient(
        [
            _extract("Ada"),
            _resp({"entity_id": existing.id}),  # resolve -> link
            _resp({"role": "Mathematician"}),  # field-extract the linked entity
        ]
    )
    editor = ScriptedEditor(unchanged)

    result = _agent(stack, stub).process_document_bulk(doc.id, editor=editor, dry_run=False)

    assert "## Links to existing entities" in editor.received
    assert result.commit_report is not None
    assert len(result.commit_report.failures) == 0

    # No new entity, field landed on the existing one, mention recorded.
    assert len(stack.entity_service.list_entities(schema="person")) == 1
    refreshed = stack.entity_service.list_entities(schema="person")[0]
    assert refreshed.fields["role"] == "Mathematician"
    assert len(mentions_for_entity(stack.root, existing.id)) == 1


def test_dry_run_collects_decisions_but_writes_nothing(tmp_path: Path) -> None:
    stack, doc = _vault_with_doc(
        tmp_path, fields=["role", "employer"], text="Ada Lovelace wrote the first algorithm."
    )
    stub = StubLlmClient(
        [
            _extract("Ada Lovelace"),
            _resp({"role": "Mathematician", "employer": ""}),
        ]
    )
    editor = ScriptedEditor(unchanged)

    result = _agent(stack, stub).process_document_bulk(doc.id, editor=editor, dry_run=True)

    assert editor.calls == 1  # editor DID open to collect decisions
    assert result.dry_run is True
    assert result.commit_report is None
    assert len(result.approved_changes) >= 2  # new entity + field-set
    assert stack.entity_service.list_entities() == []
    assert mentions_for_doc(stack.root, doc.id) == []


def test_usage_accumulates_across_all_field_extractions(tmp_path: Path) -> None:
    """Bulk mode field-extracts EVERY entity, even ones later rejected, and all
    of that usage is accumulated (the intentional divergence from option B)."""
    stack, doc = _vault_with_doc(
        tmp_path, fields=["role", "employer"], text="Ada Lovelace and Charles Babbage."
    )
    stub = StubLlmClient(
        [
            _extract(
                "Ada Lovelace", "Charles Babbage", usage=Usage(input_tokens=10, output_tokens=5)
            ),
            _resp(
                {"role": "Mathematician", "employer": ""}, Usage(input_tokens=7, output_tokens=3)
            ),
            _resp({"role": "Engineer", "employer": ""}, Usage(input_tokens=6, output_tokens=2)),
        ]
    )
    # Reject Babbage entirely; its field-extraction still ran and still counts.
    editor = ScriptedEditor(flip_to_no("c1", "c3"))

    result = _agent(stack, stub).process_document_bulk(doc.id, editor=editor, dry_run=False)

    # 10+7+6 input, 5+3+2 output -- the rejected entity's field call is included.
    assert result.usage == Usage(input_tokens=23, output_tokens=10)


def test_editor_abort_propagates_and_commits_nothing(tmp_path: Path) -> None:
    stack, doc = _vault_with_doc(
        tmp_path, fields=["role"], text="Ada Lovelace wrote the first algorithm."
    )
    stub = StubLlmClient(
        [
            _extract("Ada Lovelace"),
            _resp({"role": "Mathematician"}),
        ]
    )

    def _abort(_text: str) -> str:
        raise EditorAbortedError("user quit with :cq")

    editor = ScriptedEditor(_abort)

    with pytest.raises(EditorAbortedError):
        _agent(stack, stub).process_document_bulk(doc.id, editor=editor, dry_run=False)

    assert stack.entity_service.list_entities() == []
    assert mentions_for_doc(stack.root, doc.id) == []


def test_rename_new_entity_commits_under_new_name(tmp_path: Path) -> None:
    """Editing a proposed new entity's name creates it under the new name, and
    its field-set still lands on it (new_entity_ref unaffected by the rename)."""
    stack, doc = _vault_with_doc(
        tmp_path, fields=["role", "employer"], text="Ada wrote the first algorithm."
    )
    stub = StubLlmClient(
        [
            _extract("Ada"),  # LLM proposes the terse "Ada"
            _resp({"role": "Mathematician", "employer": ""}),
        ]
    )
    # User expands the name to the canonical form in the editor.
    editor = ScriptedEditor(rename("Ada", "Ada Lovelace"))

    result = _agent(stack, stub).process_document_bulk(doc.id, editor=editor, dry_run=False)

    assert result.commit_report is not None
    assert len(result.commit_report.failures) == 0

    entities = stack.entity_service.list_entities(schema="person")
    names = {e.name for e in entities}
    assert names == {"Ada Lovelace"}  # created under the edited name, not "Ada"
    ada = entities[0]
    assert ada.fields["role"] == "Mathematician"  # field-set followed the rename
    assert len(mentions_for_entity(stack.root, ada.id)) == 1


def test_rename_survives_promotion(tmp_path: Path) -> None:
    """A renamed new entity that is rejected but promoted (its field-set kept)
    is created under the EDITED name."""
    stack, doc = _vault_with_doc(
        tmp_path, fields=["role", "employer"], text="Ada wrote the first algorithm."
    )
    stub = StubLlmClient(
        [
            _extract("Ada"),
            _resp({"role": "Mathematician", "employer": ""}),
        ]
    )
    # all_changes: [Ada c0, fieldAda c1]. Rename AND reject the entity line,
    # but keep its field-set -> promotion recreates it under the new name.
    editor = ScriptedEditor(combine(rename("Ada", "Ada Lovelace"), flip_to_no("c0")))

    result = _agent(stack, stub).process_document_bulk(doc.id, editor=editor, dry_run=False)

    assert result.commit_report is not None
    assert len(result.commit_report.failures) == 0

    entities = stack.entity_service.list_entities(schema="person")
    assert {e.name for e in entities} == {"Ada Lovelace"}
    assert entities[0].fields["role"] == "Mathematician"


def test_zero_proposals_does_not_open_editor(tmp_path: Path) -> None:
    stack, doc = _vault_with_doc(tmp_path, fields=["role"], text="Nothing to extract.")
    stub = StubLlmClient([_resp({"entities": []})])
    editor = ScriptedEditor(unchanged)

    result = _agent(stack, stub).process_document_bulk(doc.id, editor=editor, dry_run=False)

    assert editor.calls == 0  # editor never opened
    assert result.approved_changes == []
    assert result.commit_report is not None
    assert len(result.commit_report.results) == 0
    assert stack.entity_service.list_entities() == []

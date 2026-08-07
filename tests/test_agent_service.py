"""Integration tests for AgentService.process_document (the option-B flow).

All tests run against a temp vault with a stubbed LLM boundary
(:class:`StubLlmClient`) and scripted reviewers, so they are deterministic and
free (no live model calls).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forte.model.agent import StructuredCallError
from forte.model.document import DocumentNotFoundError
from forte.model.llm import LlmResponse, Usage
from forte.service.agent._review import AutoApproveReviewer, ScriptedReviewer
from forte.service.agent._structured import MAX_RETRIES
from forte.service.agent_service import AgentService
from tests.agent_stack import Stack, build_stack, mentions_for_doc, mentions_for_entity
from tests.fake_llm_client import StubLlmClient


class FakeConfigService:
    """Stands in for ConfigService: reports a fixed extraction model."""

    def get_config(self):
        from forte.model.config import Config

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


def test_happy_path_new_entity_link_mentions_and_field_land(tmp_path: Path) -> None:
    stack, doc = _vault_with_doc(
        tmp_path, fields=["employer", "role"], text="Ada Lovelace wrote the first algorithm."
    )

    stub = StubLlmClient(
        [
            # extract-entities
            _resp(
                {
                    "entities": [
                        {
                            "name": "Ada Lovelace",
                            "schema": "person",
                            "supporting_quote": "Ada Lovelace wrote the first algorithm.",
                        }
                    ]
                },
                Usage(input_tokens=10, output_tokens=5),
            ),
            # (resolve makes NO LLM call: no existing entity matches)
            # field extraction for the approved new entity
            _resp(
                {"role": "Mathematician", "employer": ""},
                Usage(input_tokens=7, output_tokens=3),
            ),
        ]
    )

    result = _agent(stack, stub).process_document(
        doc.id, reviewer=AutoApproveReviewer(), dry_run=False
    )

    assert result.commit_report is not None
    assert len(result.commit_report.failures) == 0
    # usage accumulated across both calls
    assert result.usage == Usage(input_tokens=17, output_tokens=8)

    entities = stack.entity_service.list_entities(schema="person")
    ada = next(e for e in entities if e.name == "Ada Lovelace")
    # field-set on the NEW entity landed on the right entity (new_entity_ref alignment)
    assert ada.fields["role"] == "Mathematician"

    md_files = list((stack.root / "entities" / "person").glob("*.md"))
    assert any("ada" in f.name.lower() for f in md_files)

    mentions = mentions_for_entity(stack.root, ada.id)
    assert len(mentions) == 1
    assert mentions[0][1] == "Ada Lovelace wrote the first algorithm."


def test_rejected_entity_is_not_field_extracted_or_committed(tmp_path: Path) -> None:
    stack, doc = _vault_with_doc(
        tmp_path, fields=["employer", "role"], text="Ada Lovelace wrote the first algorithm."
    )

    # Only ONE scripted response: the extract call. resolve makes no call (no
    # match). If the rejected entity were field-extracted, the stub would
    # IndexError (exhausted) instead of returning cleanly.
    stub = StubLlmClient(
        [
            _resp(
                {
                    "entities": [
                        {
                            "name": "Ada Lovelace",
                            "schema": "person",
                            "supporting_quote": "Ada Lovelace wrote the first algorithm.",
                        }
                    ]
                }
            ),
        ]
    )

    result = _agent(stack, stub).process_document(
        doc.id, reviewer=ScriptedReviewer([False]), dry_run=False
    )

    assert result.approved_changes == []
    assert result.commit_report is not None
    assert len(result.commit_report.results) == 0
    assert stack.entity_service.list_entities(schema="person") == []
    assert mentions_for_doc(stack.root, doc.id) == []


def test_mid_run_step_failure_aborts_with_nothing_committed(tmp_path: Path) -> None:
    stack, doc = _vault_with_doc(tmp_path, fields=["role"], text="Some text.")

    # Malformed JSON for every extract-entities attempt -> StructuredCallError.
    stub = StubLlmClient(["not json"] * MAX_RETRIES)

    with pytest.raises(StructuredCallError):
        _agent(stack, stub).process_document(doc.id, reviewer=AutoApproveReviewer())

    assert stack.entity_service.list_entities() == []
    assert mentions_for_doc(stack.root, doc.id) == []


def test_zero_result_extract_returns_cleanly_and_commits_nothing(tmp_path: Path) -> None:
    stack, doc = _vault_with_doc(tmp_path, fields=["role"], text="Nothing to extract here.")

    stub = StubLlmClient([_resp({"entities": []})])

    result = _agent(stack, stub).process_document(doc.id, reviewer=AutoApproveReviewer())

    assert result.approved_changes == []
    assert result.commit_report is not None
    assert len(result.commit_report.results) == 0
    assert stack.entity_service.list_entities() == []
    assert mentions_for_doc(stack.root, doc.id) == []


def test_dry_run_runs_full_flow_but_writes_nothing(tmp_path: Path) -> None:
    stack, doc = _vault_with_doc(
        tmp_path, fields=["employer", "role"], text="Ada Lovelace wrote the first algorithm."
    )

    stub = StubLlmClient(
        [
            _resp(
                {
                    "entities": [
                        {
                            "name": "Ada Lovelace",
                            "schema": "person",
                            "supporting_quote": "Ada Lovelace wrote the first algorithm.",
                        }
                    ]
                }
            ),
            _resp({"role": "Mathematician", "employer": ""}),
        ]
    )

    result = _agent(stack, stub).process_document(
        doc.id, reviewer=AutoApproveReviewer(), dry_run=True
    )

    # full flow produced approved changes, but commit was skipped
    assert result.dry_run is True
    assert result.commit_report is None
    assert len(result.approved_changes) >= 2  # new entity + field-set
    assert stack.entity_service.list_entities() == []
    assert mentions_for_doc(stack.root, doc.id) == []


def test_link_to_existing_entity_persists_quote_and_creates_no_new_entity(
    tmp_path: Path,
) -> None:
    stack, doc = _vault_with_doc(tmp_path, fields=[], text="Ada wrote the first algorithm.")
    existing = stack.entity_service.add_entity("person", "Ada Lovelace", aliases=["Ada"])

    stub = StubLlmClient(
        [
            # extract a candidate named "Ada"
            _resp(
                {
                    "entities": [
                        {
                            "name": "Ada",
                            "schema": "person",
                            "supporting_quote": "Ada wrote the first algorithm.",
                        }
                    ]
                }
            ),
            # rule matcher finds id via alias; LLM picks that id as the link
            _resp({"entity_id": existing.id}),
        ]
    )

    result = _agent(stack, stub).process_document(
        doc.id, reviewer=AutoApproveReviewer(), dry_run=False
    )

    assert result.commit_report is not None
    assert len(result.commit_report.failures) == 0
    # no new entity created
    assert len(stack.entity_service.list_entities(schema="person")) == 1
    mentions = mentions_for_entity(stack.root, existing.id)
    assert len(mentions) == 1
    assert mentions[0][1] == "Ada wrote the first algorithm."


def test_missing_document_raises(tmp_path: Path) -> None:
    stack = build_stack(tmp_path)
    stub = StubLlmClient([])
    with pytest.raises(DocumentNotFoundError):
        _agent(stack, stub).process_document(999, reviewer=AutoApproveReviewer())


def test_format_cost_summary_uses_the_configured_extraction_model(tmp_path: Path) -> None:
    stack = build_stack(tmp_path)
    summary = _agent(stack, StubLlmClient([])).format_cost_summary(
        Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    )
    assert "input: 1000000" in summary
    assert "$6.0000" in summary

"""Integration tests for the pipeline orchestrator (agent.process_document).

All tests run against a temp vault with a stubbed LLM boundary
(:class:`StubLLMClient`) and scripted reviewers, so they are deterministic and
free (no live model calls).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forte.db.entity_repository import EntityRepository
from forte.db.mention_repository import MentionRepository
from forte.db.schema_repository import SchemaRepository
from forte.domain.schema import Schema
from forte.services.agent import process_document
from forte.services.document import DocumentNotFoundError, ingest_document
from forte.services.entity import add_entity
from forte.services.init import init
from forte.services.llm import LLMResponse, StubLLMClient
from forte.services.review import AutoApproveReviewer, ScriptedReviewer
from forte.services.structured import MAX_RETRIES, StructuredCallError
from forte.services.usage import Usage


def _vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    root.mkdir()
    init(root)
    return root


def _vault_with_doc(tmp_path: Path, *, fields: list[str], text: str):
    root = _vault(tmp_path)
    SchemaRepository(root).add(Schema(name="person", fields=fields))
    src = tmp_path / "kickoff.md"
    src.write_text(text, encoding="utf-8")
    doc = ingest_document(root, src)
    return root, doc


def _resp(payload: dict, usage: Usage | None = None) -> LLMResponse:
    return LLMResponse(text=json.dumps(payload), usage=usage or Usage.zero())


def test_happy_path_new_entity_link_mentions_and_field_land(tmp_path: Path) -> None:
    root, doc = _vault_with_doc(
        tmp_path, fields=["employer", "role"], text="Ada Lovelace wrote the first algorithm."
    )

    stub = StubLLMClient(
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

    result = process_document(
        root, doc.id, llm=stub, reviewer=AutoApproveReviewer(), dry_run=False
    )

    assert result.commit_report is not None
    assert len(result.commit_report.failures) == 0
    # usage accumulated across both calls
    assert result.usage == Usage(input_tokens=17, output_tokens=8)

    entities = EntityRepository(root).list(schema="person")
    ada = next(e for e in entities if e.name == "Ada Lovelace")
    # field-set on the NEW entity landed on the right entity (new_entity_ref alignment)
    assert ada.fields["role"] == "Mathematician"

    md_files = list((root / "entities" / "person").glob("*.md"))
    assert any("ada" in f.name.lower() for f in md_files)

    mentions = MentionRepository(root).list_for_entity(ada.id)
    assert len(mentions) == 1
    assert mentions[0].quote == "Ada Lovelace wrote the first algorithm."


def test_rejected_entity_is_not_field_extracted_or_committed(tmp_path: Path) -> None:
    root, doc = _vault_with_doc(
        tmp_path, fields=["employer", "role"], text="Ada Lovelace wrote the first algorithm."
    )

    # Only ONE scripted response: the extract call. resolve makes no call (no
    # match). If the rejected entity were field-extracted, the stub would
    # IndexError (exhausted) instead of returning cleanly.
    stub = StubLLMClient(
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

    result = process_document(
        root, doc.id, llm=stub, reviewer=ScriptedReviewer([False]), dry_run=False
    )

    assert result.approved_changes == []
    assert result.commit_report is not None
    assert len(result.commit_report.results) == 0
    assert EntityRepository(root).list(schema="person") == []
    assert MentionRepository(root).list_for_doc(doc.id) == []


def test_mid_run_step_failure_aborts_with_nothing_committed(tmp_path: Path) -> None:
    root, doc = _vault_with_doc(tmp_path, fields=["role"], text="Some text.")

    # Malformed JSON for every extract-entities attempt -> StructuredCallError.
    stub = StubLLMClient(["not json"] * MAX_RETRIES)

    with pytest.raises(StructuredCallError):
        process_document(root, doc.id, llm=stub, reviewer=AutoApproveReviewer())

    assert EntityRepository(root).list() == []
    assert MentionRepository(root).list_for_doc(doc.id) == []


def test_zero_result_extract_returns_cleanly_and_commits_nothing(tmp_path: Path) -> None:
    root, doc = _vault_with_doc(tmp_path, fields=["role"], text="Nothing to extract here.")

    stub = StubLLMClient([_resp({"entities": []})])

    result = process_document(root, doc.id, llm=stub, reviewer=AutoApproveReviewer())

    assert result.approved_changes == []
    assert result.commit_report is not None
    assert len(result.commit_report.results) == 0
    assert EntityRepository(root).list() == []
    assert MentionRepository(root).list_for_doc(doc.id) == []


def test_dry_run_runs_full_flow_but_writes_nothing(tmp_path: Path) -> None:
    root, doc = _vault_with_doc(
        tmp_path, fields=["employer", "role"], text="Ada Lovelace wrote the first algorithm."
    )

    stub = StubLLMClient(
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

    result = process_document(
        root, doc.id, llm=stub, reviewer=AutoApproveReviewer(), dry_run=True
    )

    # full flow produced approved changes, but commit was skipped
    assert result.dry_run is True
    assert result.commit_report is None
    assert len(result.approved_changes) >= 2  # new entity + field-set
    assert EntityRepository(root).list() == []
    assert MentionRepository(root).list_for_doc(doc.id) == []


def test_link_to_existing_entity_persists_quote_and_creates_no_new_entity(tmp_path: Path) -> None:
    root, doc = _vault_with_doc(tmp_path, fields=[], text="Ada wrote the first algorithm.")
    existing = add_entity(root, "person", "Ada Lovelace", aliases=["Ada"])

    stub = StubLLMClient(
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

    result = process_document(
        root, doc.id, llm=stub, reviewer=AutoApproveReviewer(), dry_run=False
    )

    assert result.commit_report is not None
    assert len(result.commit_report.failures) == 0
    # no new entity created
    assert len(EntityRepository(root).list(schema="person")) == 1
    mentions = MentionRepository(root).list_for_entity(existing.id)
    assert len(mentions) == 1
    assert mentions[0].quote == "Ada wrote the first algorithm."


def test_missing_document_raises(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    stub = StubLLMClient([])
    with pytest.raises(DocumentNotFoundError):
        process_document(root, 999, llm=stub, reviewer=AutoApproveReviewer())

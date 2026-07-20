"""Integration tests for the document service layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from forte.db.mention_repository import MentionRepository
from forte.db.schema_repository import SchemaRepository
from forte.domain.schema import Schema
from forte.domain.vault import VaultLayout
from forte.services.document import (
    DocumentNotFoundError,
    EntityNotFoundError,
    SourceFileNotFoundError,
    get_document,
    ingest_document,
    link_document,
    list_documents,
    remove_document,
    unlink_document,
)
from forte.services.entity import add_entity
from forte.services.init import init
from forte.services.text_extraction import UnsupportedFileTypeError


def _vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    root.mkdir()
    init(root)
    return root


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


# --- ingest_document ---------------------------------------------------------


def test_ingest_document_happy_path(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    src = _write(tmp_path / "kickoff.md", "hello world")

    doc = ingest_document(root, src)

    assert doc.id is not None
    assert doc.name == "kickoff.md"
    layout = VaultLayout(root)
    assert (layout.root / doc.raw_path).exists()
    assert (layout.root / doc.processed_path).exists()
    assert [d.id for d in list_documents(root)] == [doc.id]


def test_ingest_document_with_explicit_name(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    src = _write(tmp_path / "kickoff.md", "hello world")

    doc = ingest_document(root, src, name="Kickoff Notes")

    assert doc.name == "Kickoff Notes"
    assert get_document(root, doc.id).name == "Kickoff Notes"


def test_ingest_document_missing_source(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    missing = tmp_path / "missing.md"

    with pytest.raises(SourceFileNotFoundError):
        ingest_document(root, missing)

    assert list_documents(root) == []


def test_ingest_document_unsupported_type(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    src = _write(tmp_path / "diagram.png", "not really a png")

    with pytest.raises(UnsupportedFileTypeError):
        ingest_document(root, src)

    assert list_documents(root) == []


def test_ingest_document_reingest_unchanged_is_noop(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    src = _write(tmp_path / "kickoff.md", "hello world")

    first = ingest_document(root, src)
    second = ingest_document(root, src)

    assert second.id == first.id
    assert len(list_documents(root)) == 1

    layout = VaultLayout(root)
    raw_files = list((layout.root / "docs" / "raw").iterdir())
    processed_files = list((layout.root / "docs" / "processed").iterdir())
    assert len(raw_files) == 1
    assert len(processed_files) == 1


def test_ingest_document_changed_content_creates_new_doc(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    src = _write(tmp_path / "kickoff.md", "hello world")
    first = ingest_document(root, src)

    _write(src, "hello world, changed")
    second = ingest_document(root, src)

    assert second.id != first.id
    assert len(list_documents(root)) == 2


# --- list_documents / get_document -------------------------------------------


def test_list_documents_empty(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    assert list_documents(root) == []


def test_get_document_happy_path(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    src = _write(tmp_path / "kickoff.md", "hello world")
    doc = ingest_document(root, src)

    got = get_document(root, doc.id)
    assert got.id == doc.id


def test_get_document_not_found(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    with pytest.raises(DocumentNotFoundError):
        get_document(root, 999)


# --- link_document / unlink_document ------------------------------------------


def _vault_with_entity(tmp_path: Path):
    root = _vault(tmp_path)
    SchemaRepository(root).add(Schema(name="person", fields=[]))
    entity = add_entity(root, "person", "Ben")
    src = _write(tmp_path / "kickoff.md", "hello world")
    doc = ingest_document(root, src)
    return root, doc, entity


def test_link_document_happy_path(tmp_path: Path) -> None:
    root, doc, entity = _vault_with_entity(tmp_path)

    link_document(root, doc.id, entity.id)

    assert MentionRepository(root).exists(doc.id, entity.id)


def test_link_document_not_found_doc(tmp_path: Path) -> None:
    root, doc, entity = _vault_with_entity(tmp_path)

    with pytest.raises(DocumentNotFoundError):
        link_document(root, 999, entity.id)
    assert not MentionRepository(root).exists(999, entity.id)


def test_link_document_not_found_entity(tmp_path: Path) -> None:
    root, doc, entity = _vault_with_entity(tmp_path)

    with pytest.raises(EntityNotFoundError):
        link_document(root, doc.id, 999)
    assert not MentionRepository(root).exists(doc.id, 999)


def test_link_document_already_linked_is_noop(tmp_path: Path) -> None:
    root, doc, entity = _vault_with_entity(tmp_path)
    link_document(root, doc.id, entity.id)

    link_document(root, doc.id, entity.id)

    mentions = MentionRepository(root).list_for_doc(doc.id)
    assert len(mentions) == 1


def test_unlink_document_happy_path(tmp_path: Path) -> None:
    root, doc, entity = _vault_with_entity(tmp_path)
    link_document(root, doc.id, entity.id)

    unlink_document(root, doc.id, entity.id)

    assert not MentionRepository(root).exists(doc.id, entity.id)


def test_unlink_document_not_linked_is_noop(tmp_path: Path) -> None:
    root, doc, entity = _vault_with_entity(tmp_path)

    unlink_document(root, doc.id, entity.id)

    assert not MentionRepository(root).exists(doc.id, entity.id)


def test_unlink_document_not_found_doc(tmp_path: Path) -> None:
    root, doc, entity = _vault_with_entity(tmp_path)

    with pytest.raises(DocumentNotFoundError):
        unlink_document(root, 999, entity.id)


def test_unlink_document_not_found_entity(tmp_path: Path) -> None:
    root, doc, entity = _vault_with_entity(tmp_path)

    with pytest.raises(EntityNotFoundError):
        unlink_document(root, doc.id, 999)


# --- remove_document -----------------------------------------------------------


def test_remove_document_happy_path(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    src = _write(tmp_path / "kickoff.md", "hello world")
    doc = ingest_document(root, src)

    layout = VaultLayout(root)
    raw_path = layout.root / doc.raw_path
    processed_path = layout.root / doc.processed_path
    assert raw_path.exists()
    assert processed_path.exists()

    remove_document(root, doc.id)

    assert list_documents(root) == []
    assert not raw_path.exists()
    assert not processed_path.exists()
    with pytest.raises(DocumentNotFoundError):
        get_document(root, doc.id)


def test_remove_document_not_found(tmp_path: Path) -> None:
    root = _vault(tmp_path)

    with pytest.raises(DocumentNotFoundError):
        remove_document(root, 999)


def test_remove_document_cleans_up_mentions_but_not_entity(tmp_path: Path) -> None:
    root, doc, entity = _vault_with_entity(tmp_path)
    link_document(root, doc.id, entity.id)
    assert MentionRepository(root).exists(doc.id, entity.id)

    remove_document(root, doc.id)

    assert not MentionRepository(root).exists(doc.id, entity.id)
    assert MentionRepository(root).list_for_doc(doc.id) == []

    from forte.services.entity import get_entity

    still_there = get_entity(root, entity.id)
    assert still_there.id == entity.id
    assert still_there.name == entity.name

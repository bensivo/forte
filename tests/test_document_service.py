"""Unit tests for DocumentService, using fake in-memory IDocumentDb/IMentionDb/IEntityDb."""

from __future__ import annotations

from pathlib import Path

import pytest

from forte.interface.document_db import IDocumentDb
from forte.interface.entity_db import IEntityDb
from forte.interface.mention_db import IMentionDb
from forte.model.document import (
    Document,
    DocumentNotFoundError,
    SourceFileNotFoundError,
    compute_content_hash,
)
from forte.model.document_markdown import to_markdown
from forte.model.entity import Entity, EntityNotFoundError
from forte.service.document_service import DocumentService
from forte.services.text_extraction import UnsupportedFileTypeError


class FakeDocumentDb(IDocumentDb):
    def __init__(self):
        self._docs: dict[int, Document] = {}
        self._processed: dict[int, str] = {}
        self._next_id = 1

    def find_by_identity(self, source_path: str, content_hash: str) -> Document | None:
        for doc in self._docs.values():
            if doc.source_path == source_path and doc.content_hash == content_hash:
                return doc
        return None

    def add(
        self, source_path: Path, content_hash: str, extracted_text: str, name: str
    ) -> Document:
        doc_id = self._next_id
        self._next_id += 1
        stored = Document(
            name=name,
            source_path=str(source_path),
            content_hash=content_hash,
            ingested_at="2024-01-01T00:00:00+00:00",
            status="ingested",
            raw_path=f"docs/raw/{source_path.name}",
            processed_path=f"docs/processed/{doc_id}.md",
            id=doc_id,
        )
        self._docs[doc_id] = stored
        self._processed[doc_id] = to_markdown(stored, extracted_text)
        return stored

    def list(self) -> list[Document]:
        return [self._docs[i] for i in sorted(self._docs)]

    def get(self, id: int) -> Document | None:
        return self._docs.get(id)

    def read_processed(self, id: int) -> str | None:
        return self._processed.get(id)

    def remove(self, id: int) -> None:
        self._docs.pop(id, None)
        self._processed.pop(id, None)


class FakeMentionDb(IMentionDb):
    def __init__(self):
        self._mentions: set[tuple[int, int]] = set()

    def exists(self, doc_id: int, entity_id: int) -> bool:
        return (doc_id, entity_id) in self._mentions

    def add(self, doc_id: int, entity_id: int, quote: str = "") -> None:
        self._mentions.add((doc_id, entity_id))

    def remove(self, doc_id: int, entity_id: int) -> None:
        self._mentions.discard((doc_id, entity_id))

    def remove_for_doc(self, doc_id: int) -> None:
        self._mentions = {pair for pair in self._mentions if pair[0] != doc_id}


class FakeEntityDb(IEntityDb):
    def __init__(self, entities: list[Entity] | None = None):
        self._entities: dict[int, Entity] = {e.id: e for e in (entities or [])}

    def add(self, entity: Entity) -> Entity:
        raise NotImplementedError

    def get(self, entity_id: int) -> Entity | None:
        return self._entities.get(entity_id)

    def list(self, schema: str | None = None) -> list[Entity]:
        return list(self._entities.values())

    def update(self, entity: Entity) -> None:
        raise NotImplementedError

    def remove(self, entity_id: int) -> None:
        self._entities.pop(entity_id, None)


def _service(entities: list[Entity] | None = None) -> tuple[DocumentService, FakeMentionDb]:
    mention_db = FakeMentionDb()
    service = DocumentService(FakeDocumentDb(), mention_db, FakeEntityDb(entities))
    return service, mention_db


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


# --- ingest_document ---------------------------------------------------------


def test_ingest_document_happy_path(tmp_path: Path) -> None:
    service, _ = _service()
    src = _write(tmp_path / "kickoff.md", "hello world")

    doc = service.ingest_document(src)

    assert doc.id is not None
    assert doc.name == "kickoff.md"
    assert [d.id for d in service.list_documents()] == [doc.id]


def test_ingest_document_with_explicit_name(tmp_path: Path) -> None:
    service, _ = _service()
    src = _write(tmp_path / "kickoff.md", "hello world")

    doc = service.ingest_document(src, name="Kickoff Notes")

    assert doc.name == "Kickoff Notes"
    assert service.get_document(doc.id).name == "Kickoff Notes"


def test_ingest_document_missing_source(tmp_path: Path) -> None:
    service, _ = _service()
    missing = tmp_path / "missing.md"

    with pytest.raises(SourceFileNotFoundError):
        service.ingest_document(missing)

    assert service.list_documents() == []


def test_ingest_document_unsupported_type(tmp_path: Path) -> None:
    service, _ = _service()
    src = _write(tmp_path / "diagram.png", "not really a png")

    with pytest.raises(UnsupportedFileTypeError):
        service.ingest_document(src)

    assert service.list_documents() == []


def test_ingest_document_reingest_unchanged_is_noop(tmp_path: Path) -> None:
    service, _ = _service()
    src = _write(tmp_path / "kickoff.md", "hello world")

    first = service.ingest_document(src)
    second = service.ingest_document(src)

    assert second.id == first.id
    assert len(service.list_documents()) == 1


def test_ingest_document_changed_content_creates_new_doc(tmp_path: Path) -> None:
    service, _ = _service()
    src = _write(tmp_path / "kickoff.md", "hello world")
    first = service.ingest_document(src)

    _write(src, "hello world, changed")
    second = service.ingest_document(src)

    assert second.id != first.id
    assert len(service.list_documents()) == 2


# --- list_documents / get_document -------------------------------------------


def test_list_documents_empty() -> None:
    service, _ = _service()
    assert service.list_documents() == []


def test_get_document_happy_path(tmp_path: Path) -> None:
    service, _ = _service()
    src = _write(tmp_path / "kickoff.md", "hello world")
    doc = service.ingest_document(src)

    got = service.get_document(doc.id)
    assert got.id == doc.id


def test_get_document_not_found() -> None:
    service, _ = _service()
    with pytest.raises(DocumentNotFoundError):
        service.get_document(999)


# --- get_document_text --------------------------------------------------------


def test_get_document_text_returns_extracted_body(tmp_path: Path) -> None:
    service, _ = _service()
    src = _write(tmp_path / "kickoff.md", "# Kickoff\n\nAda Lovelace was there.")
    doc = service.ingest_document(src)

    text = service.get_document_text(doc.id)

    assert "Ada Lovelace was there." in text
    # frontmatter metadata is not part of the body
    assert "content_hash" not in text


def test_get_document_text_not_found() -> None:
    service, _ = _service()
    with pytest.raises(DocumentNotFoundError):
        service.get_document_text(999)


def test_get_document_text_missing_processed_copy_is_empty(tmp_path: Path) -> None:
    service, _ = _service()
    src = _write(tmp_path / "kickoff.md", "hello world")
    doc = service.ingest_document(src)
    # simulate a processed copy that is recorded but absent on disk
    service.document_db._processed.pop(doc.id)

    assert service.get_document_text(doc.id) == ""


# --- link_document / unlink_document ------------------------------------------


def _service_with_doc_and_entity(tmp_path: Path):
    entity = Entity(id=1, schema="person", name="Ben")
    service, mention_db = _service([entity])
    src = _write(tmp_path / "kickoff.md", "hello world")
    doc = service.ingest_document(src)
    return service, mention_db, doc, entity


def test_link_document_happy_path(tmp_path: Path) -> None:
    service, mention_db, doc, entity = _service_with_doc_and_entity(tmp_path)

    service.link_document(doc.id, entity.id)

    assert mention_db.exists(doc.id, entity.id)


def test_link_document_not_found_doc(tmp_path: Path) -> None:
    service, mention_db, doc, entity = _service_with_doc_and_entity(tmp_path)

    with pytest.raises(DocumentNotFoundError):
        service.link_document(999, entity.id)
    assert not mention_db.exists(999, entity.id)


def test_link_document_not_found_entity(tmp_path: Path) -> None:
    service, mention_db, doc, entity = _service_with_doc_and_entity(tmp_path)

    with pytest.raises(EntityNotFoundError):
        service.link_document(doc.id, 999)
    assert not mention_db.exists(doc.id, 999)


def test_link_document_already_linked_is_noop(tmp_path: Path) -> None:
    service, mention_db, doc, entity = _service_with_doc_and_entity(tmp_path)
    service.link_document(doc.id, entity.id)

    service.link_document(doc.id, entity.id)

    assert mention_db.exists(doc.id, entity.id)


def test_unlink_document_happy_path(tmp_path: Path) -> None:
    service, mention_db, doc, entity = _service_with_doc_and_entity(tmp_path)
    service.link_document(doc.id, entity.id)

    service.unlink_document(doc.id, entity.id)

    assert not mention_db.exists(doc.id, entity.id)


def test_unlink_document_not_linked_is_noop(tmp_path: Path) -> None:
    service, mention_db, doc, entity = _service_with_doc_and_entity(tmp_path)

    service.unlink_document(doc.id, entity.id)

    assert not mention_db.exists(doc.id, entity.id)


def test_unlink_document_not_found_doc(tmp_path: Path) -> None:
    service, mention_db, doc, entity = _service_with_doc_and_entity(tmp_path)

    with pytest.raises(DocumentNotFoundError):
        service.unlink_document(999, entity.id)


def test_unlink_document_not_found_entity(tmp_path: Path) -> None:
    service, mention_db, doc, entity = _service_with_doc_and_entity(tmp_path)

    with pytest.raises(EntityNotFoundError):
        service.unlink_document(doc.id, 999)


# --- remove_document -----------------------------------------------------------


def test_remove_document_happy_path(tmp_path: Path) -> None:
    service, _ = _service()
    src = _write(tmp_path / "kickoff.md", "hello world")
    doc = service.ingest_document(src)

    service.remove_document(doc.id)

    assert service.list_documents() == []
    with pytest.raises(DocumentNotFoundError):
        service.get_document(doc.id)


def test_remove_document_not_found() -> None:
    service, _ = _service()
    with pytest.raises(DocumentNotFoundError):
        service.remove_document(999)


def test_remove_document_cleans_up_mentions_but_not_entity(tmp_path: Path) -> None:
    service, mention_db, doc, entity = _service_with_doc_and_entity(tmp_path)
    service.link_document(doc.id, entity.id)
    assert mention_db.exists(doc.id, entity.id)

    service.remove_document(doc.id)

    assert not mention_db.exists(doc.id, entity.id)
    assert service.entity_db.get(entity.id) is not None

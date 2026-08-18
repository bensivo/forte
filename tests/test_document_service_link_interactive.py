from datetime import datetime, timezone
from typing import Callable

import pytest

from forte.interface.entity_db import IEntityDb
from forte.interface.entity_picker import IEntityPicker
from forte.interface.mention_db import IMentionDb
from forte.model.document import Document, DocumentNotFoundError
from forte.model.entity import Entity
from forte.model.entity_picker import EntityPickerAbortedError
from forte.model.mention import Mention
from forte.service.document_service import DocumentService


class FakeMentionDb(IMentionDb):
    """In-memory fake IMentionDb backed by a set of (doc_id, entity_id) pairs."""

    def __init__(self, existing: set[tuple[int, int]] | None = None):
        self._links: set[tuple[int, int]] = set(existing or set())
        self.add_calls: list[tuple[int, int, str]] = []

    def exists(self, doc_id: int, entity_id: int) -> bool:
        return (doc_id, entity_id) in self._links

    def add(self, doc_id: int, entity_id: int, quote: str = "") -> None:
        self._links.add((doc_id, entity_id))
        self.add_calls.append((doc_id, entity_id, quote))

    def list_for_doc(self, doc_id: int) -> list[Mention]:
        raise NotImplementedError

    def list_for_entity(self, entity_id: int) -> list[Mention]:
        raise NotImplementedError

    def remove(self, doc_id: int, entity_id: int) -> None:
        self._links.discard((doc_id, entity_id))

    def remove_for_doc(self, doc_id: int) -> None:
        raise NotImplementedError


class FakeEntityDb(IEntityDb):
    """In-memory fake IEntityDb backed by a dict of entities."""

    def __init__(self, entities: list[Entity]):
        self._entities = {e.id: e for e in entities}

    def add(self, entity: Entity) -> Entity:
        raise NotImplementedError

    def get(self, entity_id: int) -> Entity | None:
        return self._entities.get(entity_id)

    def list(self, schema: str | None = None) -> list[Entity]:
        raise NotImplementedError

    def update(self, entity: Entity) -> None:
        raise NotImplementedError

    def remove(self, entity_id: int) -> None:
        raise NotImplementedError


class FakeDocumentDb:
    """Minimal fake IDocumentDb; only ``get`` is exercised by
    ``link_document_interactive``."""

    def __init__(self, documents: list[Document]):
        self._documents = {doc.id: doc for doc in documents}

    def get(self, id: int) -> Document | None:
        return self._documents.get(id)


class ScriptedEntityPicker(IEntityPicker):
    """Fake IEntityPicker that returns a scripted list of entities (or
    raises a scripted error) instead of prompting a real person, and
    records the ``search`` callable it was invoked with."""

    def __init__(
        self,
        selection: list[Entity] | None = None,
        error: Exception | None = None,
    ):
        self._selection = selection or []
        self._error = error
        self.received_search: Callable[[str], list[Entity]] | None = None

    def pick(self, search: Callable[[str], list[Entity]]) -> list[Entity]:
        self.received_search = search
        if self._error is not None:
            raise self._error
        return self._selection


def _document(id: int = 1) -> Document:
    return Document(
        name="doc",
        source_path="/tmp/doc.txt",
        content_hash="hash",
        ingested_at=datetime.now(timezone.utc).isoformat(),
        status="processed",
        id=id,
    )


def _entity(id: int, name: str = "Entity") -> Entity:
    return Entity(schema="person", name=name, id=id)


def _make_service(
    *,
    documents: list[Document],
    entities: list[Entity],
    picker: IEntityPicker,
    mention_db: FakeMentionDb | None = None,
    search_entities: Callable[[str], list[Entity]] | None = None,
) -> tuple[DocumentService, FakeMentionDb]:
    mdb = mention_db if mention_db is not None else FakeMentionDb()
    service = DocumentService(
        document_db=FakeDocumentDb(documents),  # type: ignore[arg-type]
        mention_db=mdb,
        entity_db=FakeEntityDb(entities),
        editor=None,  # type: ignore[arg-type]
        document_searcher=None,  # type: ignore[arg-type]
        entity_picker=picker,
        search_entities=search_entities or (lambda q: []),
    )
    return service, mdb


def test_no_selections_links_nothing():
    # Given: a picker that returns no selections
    doc = _document(1)
    picker = ScriptedEntityPicker(selection=[])
    service, mdb = _make_service(documents=[doc], entities=[], picker=picker)

    # When: linking interactively
    linked = service.link_document_interactive(1)

    # Then: nothing was linked
    assert linked == []
    assert mdb.add_calls == []


def test_several_selections_are_linked_in_order():
    # Given: a picker that selects two entities
    doc = _document(1)
    e1 = _entity(10, "Alice")
    e2 = _entity(20, "Bob")
    picker = ScriptedEntityPicker(selection=[e2, e1])
    service, mdb = _make_service(documents=[doc], entities=[e1, e2], picker=picker)

    # When: linking interactively
    linked = service.link_document_interactive(1)

    # Then: both entities are linked, in selection order
    assert linked == [e2, e1]
    assert mdb.exists(1, 10)
    assert mdb.exists(1, 20)


def test_already_linked_entity_is_skipped_and_not_returned():
    # Given: an entity already linked to the document
    doc = _document(1)
    e1 = _entity(10, "Alice")
    e2 = _entity(20, "Bob")
    picker = ScriptedEntityPicker(selection=[e1, e2])
    mdb = FakeMentionDb(existing={(1, 10)})
    service, mdb = _make_service(
        documents=[doc], entities=[e1, e2], picker=picker, mention_db=mdb
    )

    # When: linking interactively
    linked = service.link_document_interactive(1)

    # Then: only the not-yet-linked entity is (newly) linked and returned
    assert linked == [e2]
    assert mdb.add_calls == [(1, 20, "")]


def test_deleted_entity_is_skipped_not_fatal():
    # Given: a selection including an entity that no longer exists in the
    # entity db (deleted between search and submit)
    doc = _document(1)
    e1 = _entity(10, "Alice")
    ghost = _entity(99, "Ghost")
    picker = ScriptedEntityPicker(selection=[ghost, e1])
    # Note: ghost (id=99) is not in the entities list passed to entity_db.
    service, mdb = _make_service(documents=[doc], entities=[e1], picker=picker)

    # When: linking interactively
    linked = service.link_document_interactive(1)

    # Then: the deleted entity is skipped, remaining selections still linked
    assert linked == [e1]
    assert mdb.exists(1, 10)
    assert not mdb.exists(1, 99)


def test_unknown_document_id_raises_before_picker_invoked():
    # Given: no documents exist
    picker = ScriptedEntityPicker(selection=[_entity(10)])
    service, mdb = _make_service(documents=[], entities=[_entity(10)], picker=picker)

    # When/Then: linking raises DocumentNotFoundError and the picker is
    # never invoked
    with pytest.raises(DocumentNotFoundError):
        service.link_document_interactive(1)
    assert picker.received_search is None
    assert mdb.add_calls == []


def test_aborted_picker_propagates_and_keeps_prior_links():
    # Given: a picker that raises EntityPickerAbortedError
    doc = _document(1)
    picker = ScriptedEntityPicker(error=EntityPickerAbortedError("aborted"))
    service, mdb = _make_service(documents=[doc], entities=[], picker=picker)

    # When/Then: the error propagates unchanged
    with pytest.raises(EntityPickerAbortedError):
        service.link_document_interactive(1)
    # Nothing had been linked before the abort (picker aborts before
    # returning any selections at all).
    assert mdb.add_calls == []


def test_search_callable_passed_through_to_picker_unfiltered():
    # Given: a picker recording the search callable it receives
    doc = _document(1)
    entities = [_entity(10, "Alice"), _entity(20, "Bob")]

    def search(query: str) -> list[Entity]:
        return entities

    picker = ScriptedEntityPicker(selection=[])
    service, _mdb = _make_service(
        documents=[doc], entities=entities, picker=picker, search_entities=search
    )

    # When: linking interactively
    service.link_document_interactive(1)

    # Then: the picker was given the service's search_entities callable,
    # unfiltered
    assert picker.received_search is search
    assert picker.received_search("anything") == entities

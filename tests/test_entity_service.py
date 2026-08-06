"""Unit tests for EntityService, using fake in-memory IEntityDb/ISchemaDb."""

from __future__ import annotations

import pytest

from forte.interface.entity_db import IEntityDb
from forte.interface.schema_db import ISchemaDb
from forte.model.entity import (
    Entity,
    EntityNotFoundError,
    InvalidEntityError,
    UnknownSchemaError,
)
from forte.model.schema import Schema, SchemaField
from forte.service.entity_service import EntityService, find_candidates


class FakeSchemaDb(ISchemaDb):
    def __init__(self, schemas: list[Schema] | None = None):
        self._schemas: dict[str, Schema] = {s.name: s for s in (schemas or [])}

    def check_exists(self, name: str) -> bool:
        return name in self._schemas

    def add(self, schema: Schema) -> None:
        self._schemas[schema.name] = schema

    def get(self, name: str) -> Schema | None:
        return self._schemas.get(name)

    def list(self) -> list[Schema]:
        return [self._schemas[n] for n in sorted(self._schemas)]

    def remove(self, name: str) -> None:
        self._schemas.pop(name, None)

    def count_entities(self, name: str) -> int:
        return 0


class FakeEntityDb(IEntityDb):
    def __init__(self):
        self._entities: dict[int, Entity] = {}
        self._next_id = 1

    def add(self, entity: Entity) -> Entity:
        entity_id = self._next_id
        self._next_id += 1
        stored = Entity(
            schema=entity.schema,
            name=entity.name,
            aliases=list(entity.aliases),
            fields=dict(entity.fields),
            body=entity.body,
            id=entity_id,
            file_path=f"{entity.schema}/{entity.name}.md",
        )
        self._entities[entity_id] = stored
        return stored

    def get(self, entity_id: int) -> Entity | None:
        return self._entities.get(entity_id)

    def list(self, schema: str | None = None) -> list[Entity]:
        entities = [self._entities[i] for i in sorted(self._entities)]
        if schema is not None:
            entities = [e for e in entities if e.schema == schema]
        return entities

    def update(self, entity: Entity) -> None:
        self._entities[entity.id] = entity

    def remove(self, entity_id: int) -> None:
        self._entities.pop(entity_id, None)


def _service(*schemas: Schema) -> EntityService:
    return EntityService(FakeEntityDb(), FakeSchemaDb(list(schemas)))


def _person_schema(*fields: str) -> Schema:
    return Schema(name="person", fields=[SchemaField(name=f) for f in fields])


# --- add_entity: happy paths -------------------------------------------------


def test_add_entity_returns_entity_with_id() -> None:
    service = _service(_person_schema("employer", "role"))

    entity = service.add_entity(
        "person",
        "Ben Sivongxay",
        aliases=["Ben"],
        field_values={"employer": "Acme", "role": "Engineer"},
    )

    assert entity.id is not None
    assert entity.name == "Ben Sivongxay"
    assert entity.aliases == ["Ben"]
    assert entity.fields == {"employer": "Acme", "role": "Engineer"}


def test_add_entity_backfills_omitted_fields_in_schema_order() -> None:
    service = _service(_person_schema("employer", "role", "city"))

    entity = service.add_entity("person", "Ben", field_values={"role": "Engineer"})

    assert list(entity.fields.keys()) == ["employer", "role", "city"]
    assert entity.fields == {"employer": "", "role": "Engineer", "city": ""}


def test_add_entity_name_only_backfills_all() -> None:
    service = _service(_person_schema("employer", "role"))

    entity = service.add_entity("person", "Ben")

    assert entity.fields == {"employer": "", "role": ""}
    assert entity.aliases == []


def test_add_entity_zero_field_schema() -> None:
    service = _service(Schema(name="note", fields=[]))

    entity = service.add_entity("note", "Idea")

    assert entity.fields == {}


def test_add_entity_persists_visible_via_list_and_get() -> None:
    service = _service(_person_schema("employer"))

    entity = service.add_entity("person", "Ben", field_values={"employer": "Acme"})

    assert [e.id for e in service.list_entities()] == [entity.id]
    assert service.get_entity(entity.id).name == "Ben"


# --- add_entity: validation branches ----------------------------------------


def test_add_entity_unknown_schema() -> None:
    service = _service()

    with pytest.raises(UnknownSchemaError):
        service.add_entity("person", "Ben")

    assert service.list_entities() == []


@pytest.mark.parametrize("bad_name", ["", "   "])
def test_add_entity_missing_name(bad_name: str) -> None:
    service = _service(_person_schema("role"))

    with pytest.raises(InvalidEntityError):
        service.add_entity("person", bad_name)

    assert service.list_entities() == []


def test_add_entity_unknown_field() -> None:
    service = _service(_person_schema("role"))

    with pytest.raises(InvalidEntityError):
        service.add_entity("person", "Ben", field_values={"salary": "100"})

    assert service.list_entities() == []


# --- list_entities -------------------------------------------------------------


def test_list_entities_empty() -> None:
    service = _service(_person_schema())

    assert service.list_entities() == []


def test_list_entities_filters_by_schema() -> None:
    service = _service(
        _person_schema("role"),
        Schema(name="company", fields=[SchemaField(name="industry")]),
    )
    service.add_entity("person", "Ben")
    service.add_entity("company", "Acme")
    service.add_entity("person", "Ana")

    assert [e.name for e in service.list_entities()] == ["Ben", "Acme", "Ana"]
    assert [e.name for e in service.list_entities(schema="person")] == ["Ben", "Ana"]
    assert [e.name for e in service.list_entities(schema="company")] == ["Acme"]


def test_list_entities_unknown_schema_filter_raises() -> None:
    service = _service(_person_schema())

    with pytest.raises(UnknownSchemaError):
        service.list_entities(schema="nope")


# --- get_entity ----------------------------------------------------------------


def test_get_entity_happy_path() -> None:
    service = _service(_person_schema("role"))
    entity = service.add_entity("person", "Ben")

    assert service.get_entity(entity.id).name == "Ben"


def test_get_entity_not_found() -> None:
    service = _service(_person_schema())

    with pytest.raises(EntityNotFoundError):
        service.get_entity(999)


# --- edit_entity -----------------------------------------------------------------


def test_edit_entity_changes_name() -> None:
    service = _service(_person_schema("role"))
    entity = service.add_entity("person", "Ben")

    edited = service.edit_entity(entity.id, name="Benjamin")

    assert edited.name == "Benjamin"


def test_edit_entity_sets_field_value() -> None:
    service = _service(_person_schema("employer", "role"))
    entity = service.add_entity("person", "Ben")

    edited = service.edit_entity(entity.id, set_fields={"role": "Engineer"})

    assert edited.fields == {"employer": "", "role": "Engineer"}


def test_edit_entity_add_and_remove_aliases() -> None:
    service = _service(_person_schema("role"))
    entity = service.add_entity("person", "Ben", aliases=["B"])

    edited = service.edit_entity(
        entity.id,
        add_aliases=["Ben S.", "B"],
        remove_aliases=["missing"],
    )
    assert edited.aliases == ["B", "Ben S."]

    edited2 = service.edit_entity(entity.id, remove_aliases=["B"])
    assert edited2.aliases == ["Ben S."]


def test_edit_entity_preserves_field_set_invariant() -> None:
    service = _service(_person_schema("employer", "role"))
    entity = service.add_entity("person", "Ben", field_values={"employer": "Acme"})

    edited = service.edit_entity(entity.id, set_fields={"role": "Engineer"})

    assert list(edited.fields.keys()) == ["employer", "role"]
    assert edited.fields == {"employer": "Acme", "role": "Engineer"}


def test_edit_entity_unknown_field_errors_and_no_write() -> None:
    service = _service(_person_schema("role"))
    entity = service.add_entity("person", "Ben", field_values={"role": "Engineer"})

    with pytest.raises(InvalidEntityError):
        service.edit_entity(entity.id, set_fields={"salary": "100"})

    assert service.get_entity(entity.id).fields == {"role": "Engineer"}


def test_edit_entity_empty_name_errors() -> None:
    service = _service(_person_schema("role"))
    entity = service.add_entity("person", "Ben")

    with pytest.raises(InvalidEntityError):
        service.edit_entity(entity.id, name="   ")

    assert service.get_entity(entity.id).name == "Ben"


def test_edit_entity_not_found() -> None:
    service = _service(_person_schema())

    with pytest.raises(EntityNotFoundError):
        service.edit_entity(999, name="Nope")


def test_edit_entity_unknown_schema() -> None:
    entity_db = FakeEntityDb()
    schema_db = FakeSchemaDb([_person_schema("role")])
    service = EntityService(entity_db, schema_db)
    entity = service.add_entity("person", "Ben")

    schema_db.remove("person")

    with pytest.raises(UnknownSchemaError):
        service.edit_entity(entity.id, name="Benjamin")


# --- remove_entity -----------------------------------------------------------


def test_remove_entity_happy_path() -> None:
    service = _service(_person_schema("role"))
    entity = service.add_entity("person", "Ben")

    service.remove_entity(entity.id)

    assert service.list_entities() == []
    with pytest.raises(EntityNotFoundError):
        service.get_entity(entity.id)


def test_remove_entity_not_found() -> None:
    service = _service(_person_schema())

    with pytest.raises(EntityNotFoundError):
        service.remove_entity(999)


# --- find_candidates (folded-in linking module) -------------------------------


def test_find_candidates_exact_name_match() -> None:
    entities = [Entity(id=1, schema="person", name="Ada Lovelace")]
    result = find_candidates("Ada Lovelace", "person", entities)
    assert result == [entities[0]]


def test_find_candidates_exact_alias_match() -> None:
    entities = [Entity(id=1, schema="person", name="Ada Lovelace", aliases=["Ada"])]
    result = find_candidates("Ada", "person", entities)
    assert result == [entities[0]]


def test_find_candidates_normalized_name_match_case_and_whitespace() -> None:
    entities = [Entity(id=1, schema="person", name="Ada  Lovelace")]
    result = find_candidates("ada lovelace", "person", entities)
    assert result == [entities[0]]


def test_find_candidates_normalized_alias_match_case_and_whitespace() -> None:
    entities = [
        Entity(id=1, schema="person", name="Ada Lovelace", aliases=["Countess  Lovelace"])
    ]
    result = find_candidates("countess lovelace", "person", entities)
    assert result == [entities[0]]


def test_find_candidates_no_match_returns_empty_list() -> None:
    entities = [Entity(id=1, schema="person", name="Ada Lovelace")]
    result = find_candidates("Charles Babbage", "person", entities)
    assert result == []


def test_find_candidates_schema_scoping_same_string_different_schema_no_match() -> None:
    entities = [Entity(id=1, schema="project", name="Apollo")]
    result = find_candidates("Apollo", "person", entities)
    assert result == []


def test_find_candidates_deduplication_when_entity_matches_multiple_ways() -> None:
    entities = [
        Entity(id=1, schema="person", name="Ada Lovelace", aliases=["ada lovelace"])
    ]
    result = find_candidates("Ada Lovelace", "person", entities)
    assert result == [entities[0]]


def test_find_candidates_works_with_plain_list_of_entities_no_db() -> None:
    entities = [
        Entity(id=2, schema="person", name="Bob"),
        Entity(id=1, schema="person", name="Bob"),
    ]
    result = find_candidates("Bob", "person", entities)
    assert [e.id for e in result] == [1, 2]

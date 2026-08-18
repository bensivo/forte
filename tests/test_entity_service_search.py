from forte.interface.entity_db import IEntityDb
from forte.model.entity import Entity
from forte.service.entity_service import EntityService


class FakeEntityDb(IEntityDb):
    """Fake IEntityDb backed by an in-memory dict of entities."""

    def __init__(self, entities: list[Entity]):
        self._entities = {e.id: e for e in entities}

    def add(self, entity: Entity) -> Entity:
        raise NotImplementedError

    def get(self, entity_id: int) -> Entity | None:
        return self._entities.get(entity_id)

    def list(self, schema: str | None = None) -> list[Entity]:
        entities = list(self._entities.values())
        if schema is not None:
            entities = [e for e in entities if e.schema == schema]
        return sorted(entities, key=lambda e: e.id or 0)

    def update(self, entity: Entity) -> None:
        raise NotImplementedError

    def remove(self, entity_id: int) -> None:
        raise NotImplementedError


def _entity(id: int, schema: str, name: str, aliases: list[str] | None = None) -> Entity:
    return Entity(schema=schema, name=name, aliases=aliases or [], id=id)


def _make_service(entities: list[Entity]) -> EntityService:
    return EntityService(
        entity_db=FakeEntityDb(entities),
        schema_db=None,  # type: ignore[arg-type]
        mention_db=None,  # type: ignore[arg-type]
        document_db=None,  # type: ignore[arg-type]
    )


def test_matches_on_name_substring():
    # Given: an entity whose name contains the query
    alice = _entity(1, "person", "Alice")
    service = _make_service([alice])

    # When: searching for a substring of the name
    results = service.search_entities("lic")

    # Then: the entity is returned
    assert results == [alice]


def test_matches_on_alias_substring():
    # Given: an entity whose alias (but not name) contains the query
    bob = _entity(1, "person", "Robert", aliases=["Bobby"])
    service = _make_service([bob])

    # When: searching for a substring of the alias
    results = service.search_entities("obb")

    # Then: the entity is returned via its alias
    assert results == [bob]


def test_search_is_case_insensitive():
    # Given: an entity named in mixed case
    alice = _entity(1, "person", "Alice")
    service = _make_service([alice])

    # When: searching with a differently-cased query
    results = service.search_entities("ALI")

    # Then: the entity still matches
    assert results == [alice]


def test_query_is_normalized_like_names():
    # Given: an entity named "Alice"
    alice = _entity(1, "person", "Alice")
    service = _make_service([alice])

    # When: searching with extra surrounding/internal whitespace
    results = service.search_entities("  ali ")

    # Then: it behaves the same as the trimmed query
    assert results == service.search_entities("ali")
    assert results == [alice]


def test_search_is_cross_schema():
    # Given: entities with the same matching substring across two schemas
    alice_person = _entity(1, "person", "Alice")
    alice_contact = _entity(2, "contact", "Alice Corp")
    service = _make_service([alice_person, alice_contact])

    # When: searching without restricting schema
    results = service.search_entities("ali")

    # Then: both entities, regardless of schema, are returned
    assert {e.id for e in results} == {1, 2}


def test_name_matches_rank_before_alias_only_matches():
    # Given: one entity matching by name, another matching only by alias
    by_alias = _entity(1, "person", "Robert", aliases=["Ali G"])
    by_name = _entity(2, "person", "Alice")
    service = _make_service([by_alias, by_name])

    # When: searching for a query that matches both, differently
    results = service.search_entities("ali")

    # Then: the name match is ranked first
    assert [e.id for e in results] == [2, 1]


def test_prefix_matches_rank_before_mid_string_matches():
    # Given: one entity whose name has the query mid-string, another as a prefix
    natalie = _entity(1, "person", "Natalie")
    alice = _entity(2, "person", "Alice")
    service = _make_service([natalie, alice])

    # When: searching with a query that is a prefix of one name
    results = service.search_entities("ali")

    # Then: the prefix match (Alice) ranks before the mid-string match (Natalie)
    assert [e.id for e in results] == [2, 1]


def test_ties_broken_by_ascending_entity_id():
    # Given: two entities with identically-ranked matches
    b = _entity(2, "person", "Alice B")
    a = _entity(1, "person", "Alice A")
    service = _make_service([b, a])

    # When: searching
    results = service.search_entities("alice")

    # Then: results are ordered by ascending id
    assert [e.id for e in results] == [1, 2]


def test_entity_matching_both_name_and_alias_appears_once():
    # Given: an entity whose name and alias both contain the query
    entity = _entity(1, "person", "Alice", aliases=["Alicia"])
    service = _make_service([entity])

    # When: searching for a substring common to both
    results = service.search_entities("ali")

    # Then: it appears exactly once
    assert results == [entity]


def test_empty_query_returns_all_entities():
    # Given: several entities
    a = _entity(1, "person", "Alice")
    b = _entity(2, "person", "Bob")
    service = _make_service([b, a])

    # When: searching with an empty query
    results = service.search_entities("")

    # Then: all entities are returned, ordered deterministically
    assert [e.id for e in results] == [1, 2]


def test_whitespace_only_query_returns_all_entities():
    # Given: several entities
    a = _entity(1, "person", "Alice")
    b = _entity(2, "person", "Bob")
    service = _make_service([a, b])

    # When: searching with a whitespace-only query
    results = service.search_entities("   ")

    # Then: all entities are returned rather than raising
    assert [e.id for e in results] == [1, 2]


def test_limit_caps_results_after_ranking():
    # Given: three entities that all match
    a = _entity(1, "person", "Alice")
    b = _entity(2, "person", "Ali")
    c = _entity(3, "person", "Natalie")
    service = _make_service([a, b, c])

    # When: searching with a limit smaller than the match count
    results = service.search_entities("ali", limit=2)

    # Then: only the top-ranked `limit` results are returned (both name
    # prefix matches, ranked by ascending id ahead of the mid-string match)
    assert len(results) == 2
    assert [e.id for e in results] == [1, 2]


def test_no_match_returns_empty_list():
    # Given: an entity that does not contain the query
    alice = _entity(1, "person", "Alice")
    service = _make_service([alice])

    # When: searching for a non-matching substring
    results = service.search_entities("xyz")

    # Then: no results are returned
    assert results == []

"""Unit/integration tests for the entity service layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from forte.db.schema_repository import SchemaRepository
from forte.domain.entity_markdown import from_markdown
from forte.domain.schema import Schema
from forte.domain.vault import VaultLayout
from forte.services.entity import (
    EntityNotFoundError,
    InvalidEntityError,
    UnknownSchemaError,
    add_entity,
    edit_entity,
    get_entity,
    list_entities,
    remove_entity,
)
from forte.services.init import init


def _vault(tmp_path: Path, *schemas: Schema) -> Path:
    """Create an initialized vault with the given schemas defined."""
    init(tmp_path)
    schema_repo = SchemaRepository(tmp_path)
    for schema in schemas:
        schema_repo.add(schema)
    return tmp_path


# --- add_entity: happy paths -------------------------------------------------


def test_add_entity_returns_entity_with_id(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person", fields=["employer", "role"]))

    entity = add_entity(
        root,
        "person",
        "Ben Sivongxay",
        aliases=["Ben"],
        field_values={"employer": "Acme", "role": "Engineer"},
    )

    assert entity.id is not None
    assert entity.name == "Ben Sivongxay"
    assert entity.aliases == ["Ben"]
    assert entity.fields == {"employer": "Acme", "role": "Engineer"}


def test_add_entity_backfills_omitted_fields_in_schema_order(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person", fields=["employer", "role", "city"]))

    entity = add_entity(root, "person", "Ben", field_values={"role": "Engineer"})

    # Exactly the schema's field set, in schema order, missing ones back-filled.
    assert list(entity.fields.keys()) == ["employer", "role", "city"]
    assert entity.fields == {"employer": "", "role": "Engineer", "city": ""}


def test_add_entity_name_only_backfills_all(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person", fields=["employer", "role"]))

    entity = add_entity(root, "person", "Ben")

    assert entity.fields == {"employer": "", "role": ""}
    assert entity.aliases == []


def test_add_entity_zero_field_schema(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="note", fields=[]))

    entity = add_entity(root, "note", "Idea")

    assert entity.fields == {}


def test_add_entity_persists_to_disk_and_db(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person", fields=["employer"]))

    entity = add_entity(
        root, "person", "Ben", field_values={"employer": "Acme"}
    )

    # Visible via list/get.
    assert [e.id for e in list_entities(root)] == [entity.id]
    assert get_entity(root, entity.id).name == "Ben"

    # Markdown file present with the right frontmatter.
    path = VaultLayout(root).entities_dir / "person" / "ben.md"
    parsed = from_markdown(path.read_text(encoding="utf-8"))
    assert parsed.name == "Ben"
    assert parsed.fields == {"employer": "Acme"}


# --- add_entity: validation branches ----------------------------------------


def test_add_entity_unknown_schema(tmp_path: Path) -> None:
    root = _vault(tmp_path)

    with pytest.raises(UnknownSchemaError):
        add_entity(root, "person", "Ben")

    assert list_entities(root) == []


@pytest.mark.parametrize("bad_name", ["", "   "])
def test_add_entity_missing_name(tmp_path: Path, bad_name: str) -> None:
    root = _vault(tmp_path, Schema(name="person", fields=["role"]))

    with pytest.raises(InvalidEntityError):
        add_entity(root, "person", bad_name)

    assert list_entities(root) == []


def test_add_entity_unknown_field(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person", fields=["role"]))

    with pytest.raises(InvalidEntityError):
        add_entity(root, "person", "Ben", field_values={"salary": "100"})

    # No partial write.
    assert list_entities(root) == []


# --- list_entities -----------------------------------------------------------


def test_list_entities_empty(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person"))

    assert list_entities(root) == []


def test_list_entities_filters_by_schema(tmp_path: Path) -> None:
    root = _vault(
        tmp_path,
        Schema(name="person", fields=["role"]),
        Schema(name="company", fields=["industry"]),
    )
    add_entity(root, "person", "Ben")
    add_entity(root, "company", "Acme")
    add_entity(root, "person", "Ana")

    assert [e.name for e in list_entities(root)] == ["Ben", "Acme", "Ana"]
    assert [e.name for e in list_entities(root, schema="person")] == ["Ben", "Ana"]
    assert [e.name for e in list_entities(root, schema="company")] == ["Acme"]


def test_list_entities_unknown_schema_filter_raises(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person"))

    with pytest.raises(UnknownSchemaError):
        list_entities(root, schema="nope")


# --- get_entity --------------------------------------------------------------


def test_get_entity_happy_path(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person", fields=["role"]))
    entity = add_entity(root, "person", "Ben")

    got = get_entity(root, entity.id)
    assert got.name == "Ben"


def test_get_entity_not_found(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person"))

    with pytest.raises(EntityNotFoundError):
        get_entity(root, 999)


# --- edit_entity -------------------------------------------------------------


def test_edit_entity_changes_name_and_renames_file(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person", fields=["role"]))
    entity = add_entity(root, "person", "Ben")
    layout = VaultLayout(root)
    old_path = layout.entities_dir / "person" / "ben.md"
    assert old_path.is_file()

    edited = edit_entity(root, entity.id, name="Benjamin")

    assert edited.name == "Benjamin"
    new_path = layout.entities_dir / "person" / "benjamin.md"
    assert new_path.is_file()
    assert not old_path.exists()


def test_edit_entity_sets_field_value(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person", fields=["employer", "role"]))
    entity = add_entity(root, "person", "Ben")

    edited = edit_entity(root, entity.id, set_fields={"role": "Engineer"})

    assert edited.fields == {"employer": "", "role": "Engineer"}
    # Reflected on disk.
    path = VaultLayout(root).entities_dir / "person" / "ben.md"
    parsed = from_markdown(path.read_text(encoding="utf-8"))
    assert parsed.fields["role"] == "Engineer"


def test_edit_entity_add_and_remove_aliases(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person", fields=["role"]))
    entity = add_entity(root, "person", "Ben", aliases=["B"])

    edited = edit_entity(
        root,
        entity.id,
        add_aliases=["Ben S.", "B"],  # "B" already present → no duplicate
        remove_aliases=["missing"],  # not present → no-op
    )
    assert edited.aliases == ["B", "Ben S."]

    edited2 = edit_entity(root, entity.id, remove_aliases=["B"])
    assert edited2.aliases == ["Ben S."]


def test_edit_entity_preserves_field_set_invariant(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person", fields=["employer", "role"]))
    entity = add_entity(root, "person", "Ben", field_values={"employer": "Acme"})

    edited = edit_entity(root, entity.id, set_fields={"role": "Engineer"})

    # Field set stays exactly the schema's, in order; other values preserved.
    assert list(edited.fields.keys()) == ["employer", "role"]
    assert edited.fields == {"employer": "Acme", "role": "Engineer"}


def test_edit_entity_unknown_field_errors_and_no_write(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person", fields=["role"]))
    entity = add_entity(root, "person", "Ben", field_values={"role": "Engineer"})

    with pytest.raises(InvalidEntityError):
        edit_entity(root, entity.id, set_fields={"salary": "100"})

    # Unchanged.
    got = get_entity(root, entity.id)
    assert got.fields == {"role": "Engineer"}


def test_edit_entity_empty_name_errors(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person", fields=["role"]))
    entity = add_entity(root, "person", "Ben")

    with pytest.raises(InvalidEntityError):
        edit_entity(root, entity.id, name="   ")

    assert get_entity(root, entity.id).name == "Ben"


def test_edit_entity_not_found(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person"))

    with pytest.raises(EntityNotFoundError):
        edit_entity(root, 999, name="Nope")


# --- remove_entity -----------------------------------------------------------


def test_remove_entity_happy_path(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person", fields=["role"]))
    entity = add_entity(root, "person", "Ben")
    path = VaultLayout(root).entities_dir / "person" / "ben.md"
    assert path.is_file()

    remove_entity(root, entity.id)

    assert list_entities(root) == []
    assert not path.exists()
    with pytest.raises(EntityNotFoundError):
        get_entity(root, entity.id)


def test_remove_entity_not_found(tmp_path: Path) -> None:
    root = _vault(tmp_path, Schema(name="person"))

    with pytest.raises(EntityNotFoundError):
        remove_entity(root, 999)

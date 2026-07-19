"""Integration tests for the entity DB repository (real SQLite + real files)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from forte.db.entity_repository import EntityRepository
from forte.db.schema_repository import SchemaRepository
from forte.domain.entity import Entity
from forte.domain.entity_markdown import from_markdown
from forte.domain.schema import Schema
from forte.domain.vault import VaultLayout
from forte.services.init import init


def _vault(tmp_path: Path, *schemas: Schema) -> Path:
    """Create an initialized vault with the given schemas defined."""
    init(tmp_path)
    schema_repo = SchemaRepository(tmp_path)
    for schema in schemas:
        schema_repo.add(schema)
    return tmp_path


def _row(db_path: Path, entity_id: int) -> tuple | None:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT id, schema, name, aliases_json, fields_json, file_path "
            "FROM entities WHERE id = ?",
            (entity_id,),
        ).fetchone()


def test_add_writes_file_and_row(tmp_path: Path) -> None:
    _vault(tmp_path, Schema(name="person", fields=["employer", "role"]))
    repo = EntityRepository(tmp_path)
    layout = VaultLayout(tmp_path)

    stored = repo.add(
        Entity(
            schema="person",
            name="Ben Sivongxay",
            aliases=["Ben"],
            fields={"employer": "Acme", "role": "Engineer"},
        )
    )

    assert stored.id is not None
    assert stored.file_path == "entities/person/ben-sivongxay.md"

    path = layout.entities_dir / "person" / "ben-sivongxay.md"
    assert path.is_file()

    parsed = from_markdown(path.read_text(encoding="utf-8"))
    assert parsed.name == "Ben Sivongxay"
    assert parsed.aliases == ["Ben"]
    assert parsed.fields == {"employer": "Acme", "role": "Engineer"}

    row = _row(layout.db_path, stored.id)
    assert row is not None
    assert row[1] == "person"
    assert row[2] == "Ben Sivongxay"
    assert row[5] == "entities/person/ben-sivongxay.md"


def test_add_missing_schema_folder_fails_loudly(tmp_path: Path) -> None:
    init(tmp_path)  # no schema added
    repo = EntityRepository(tmp_path)

    with pytest.raises(FileNotFoundError):
        repo.add(Entity(schema="person", name="Ben"))

    # Nothing should have been inserted.
    assert repo.list() == []


def test_get_round_trips_fields_and_aliases(tmp_path: Path) -> None:
    _vault(tmp_path, Schema(name="person", fields=["employer", "role", "city"]))
    repo = EntityRepository(tmp_path)

    stored = repo.add(
        Entity(
            schema="person",
            name="Ana",
            aliases=["A", "Annie"],
            fields={"employer": "Globex", "role": "", "city": "NYC"},
        )
    )

    got = repo.get(stored.id)
    assert got is not None
    assert got.name == "Ana"
    assert got.aliases == ["A", "Annie"]
    # Field order preserved.
    assert list(got.fields.keys()) == ["employer", "role", "city"]
    assert got.fields == {"employer": "Globex", "role": "", "city": "NYC"}


def test_get_missing_returns_none(tmp_path: Path) -> None:
    _vault(tmp_path, Schema(name="person"))
    repo = EntityRepository(tmp_path)

    assert repo.get(999) is None


def test_list_orders_by_id_and_filters_by_schema(tmp_path: Path) -> None:
    _vault(
        tmp_path,
        Schema(name="person", fields=["role"]),
        Schema(name="company", fields=["industry"]),
    )
    repo = EntityRepository(tmp_path)

    e1 = repo.add(Entity(schema="person", name="Ben"))
    e2 = repo.add(Entity(schema="company", name="Acme"))
    e3 = repo.add(Entity(schema="person", name="Ana"))

    all_ids = [e.id for e in repo.list()]
    assert all_ids == [e1.id, e2.id, e3.id]

    persons = repo.list(schema="person")
    assert [e.name for e in persons] == ["Ben", "Ana"]

    companies = repo.list(schema="company")
    assert [e.name for e in companies] == ["Acme"]


def test_update_reflects_in_file_and_row(tmp_path: Path) -> None:
    _vault(tmp_path, Schema(name="person", fields=["employer", "role"]))
    repo = EntityRepository(tmp_path)
    layout = VaultLayout(tmp_path)

    stored = repo.add(
        Entity(
            schema="person",
            name="Ben",
            aliases=["B"],
            fields={"employer": "Acme", "role": "Engineer"},
        )
    )

    stored.fields["role"] = "Manager"
    stored.aliases.append("Benny")
    repo.update(stored)

    got = repo.get(stored.id)
    assert got is not None
    assert got.fields["role"] == "Manager"
    assert got.aliases == ["B", "Benny"]

    path = layout.entities_dir / "person" / "ben.md"
    parsed = from_markdown(path.read_text(encoding="utf-8"))
    assert parsed.fields["role"] == "Manager"
    assert parsed.aliases == ["B", "Benny"]


def test_update_rename_moves_file(tmp_path: Path) -> None:
    _vault(tmp_path, Schema(name="person", fields=["role"]))
    repo = EntityRepository(tmp_path)
    layout = VaultLayout(tmp_path)

    stored = repo.add(Entity(schema="person", name="Ben"))
    old_path = layout.entities_dir / "person" / "ben.md"
    assert old_path.is_file()

    stored.name = "Benjamin"
    repo.update(stored)

    new_path = layout.entities_dir / "person" / "benjamin.md"
    assert new_path.is_file()
    assert not old_path.exists()

    got = repo.get(stored.id)
    assert got is not None
    assert got.file_path == "entities/person/benjamin.md"


def test_remove_deletes_file_and_row(tmp_path: Path) -> None:
    _vault(tmp_path, Schema(name="person", fields=["role"]))
    repo = EntityRepository(tmp_path)
    layout = VaultLayout(tmp_path)

    stored = repo.add(Entity(schema="person", name="Ben"))
    path = layout.entities_dir / "person" / "ben.md"
    assert path.is_file()

    repo.remove(stored.id)

    assert repo.get(stored.id) is None
    assert _row(layout.db_path, stored.id) is None
    assert not path.exists()


def test_slug_collision_disambiguates(tmp_path: Path) -> None:
    _vault(tmp_path, Schema(name="person", fields=["role"]))
    repo = EntityRepository(tmp_path)
    layout = VaultLayout(tmp_path)

    first = repo.add(Entity(schema="person", name="Ben"))
    second = repo.add(Entity(schema="person", name="Ben"))

    assert first.file_path == "entities/person/ben.md"
    # Second entity with the same name must not overwrite the first.
    assert second.file_path == f"entities/person/ben-{second.id}.md"

    first_path = layout.entities_dir / "person" / "ben.md"
    second_path = layout.entities_dir / "person" / f"ben-{second.id}.md"
    assert first_path.is_file()
    assert second_path.is_file()

    # Both remain independently retrievable.
    assert repo.get(first.id).name == "Ben"
    assert repo.get(second.id).name == "Ben"

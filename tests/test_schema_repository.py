"""Integration tests for the schema DB repository (real SQLite + real folders)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from forte.db.schema_repository import SchemaRepository
from forte.domain.schema import Schema
from forte.domain.vault import VaultLayout
from forte.services.init import init


def _schema_names(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM schemas").fetchall()
    return {r[0] for r in rows}


def test_add_creates_db_row_and_folder(tmp_path: Path) -> None:
    init(tmp_path)
    repo = SchemaRepository(tmp_path)
    layout = VaultLayout(tmp_path)

    repo.add(Schema(name="person", fields=["employer", "role"]))

    assert "person" in _schema_names(layout.db_path)
    assert (layout.entities_dir / "person").is_dir()


def test_add_with_zero_fields(tmp_path: Path) -> None:
    init(tmp_path)
    repo = SchemaRepository(tmp_path)

    repo.add(Schema(name="note"))

    stored = repo.get("note")
    assert stored is not None
    assert stored.fields == []


def test_list_and_get_round_trip_field_order(tmp_path: Path) -> None:
    init(tmp_path)
    repo = SchemaRepository(tmp_path)

    repo.add(Schema(name="person", fields=["employer", "role", "city"]))
    repo.add(Schema(name="company", fields=["industry", "hq"]))

    got = repo.get("person")
    assert got == Schema(name="person", fields=["employer", "role", "city"])
    # Field order must be preserved exactly, not sorted.
    assert got.fields == ["employer", "role", "city"]

    listed = repo.list()
    assert [s.name for s in listed] == ["company", "person"]
    by_name = {s.name: s for s in listed}
    assert by_name["person"].fields == ["employer", "role", "city"]
    assert by_name["company"].fields == ["industry", "hq"]


def test_get_missing_returns_none(tmp_path: Path) -> None:
    init(tmp_path)
    repo = SchemaRepository(tmp_path)

    assert repo.get("nope") is None


def test_exists(tmp_path: Path) -> None:
    init(tmp_path)
    repo = SchemaRepository(tmp_path)

    assert repo.exists("person") is False
    repo.add(Schema(name="person", fields=["role"]))
    assert repo.exists("person") is True


def test_remove_deletes_row_and_folder(tmp_path: Path) -> None:
    init(tmp_path)
    repo = SchemaRepository(tmp_path)
    layout = VaultLayout(tmp_path)

    repo.add(Schema(name="person", fields=["role"]))
    assert (layout.entities_dir / "person").is_dir()

    repo.remove("person")

    assert "person" not in _schema_names(layout.db_path)
    assert not (layout.entities_dir / "person").exists()


def test_remove_refuses_nonempty_folder(tmp_path: Path) -> None:
    init(tmp_path)
    repo = SchemaRepository(tmp_path)
    layout = VaultLayout(tmp_path)

    repo.add(Schema(name="person", fields=["role"]))
    (layout.entities_dir / "person" / "alice.md").write_text("stub\n")

    with pytest.raises(OSError):
        repo.remove("person")

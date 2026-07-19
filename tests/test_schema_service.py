"""Unit/integration tests for the schema service layer."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from forte.domain.schema import Schema
from forte.domain.vault import VaultLayout
from forte.services.init import init
from forte.services.schema import (
    InvalidSchemaError,
    SchemaExistsError,
    SchemaInUseError,
    SchemaNotFoundError,
    add_schema,
    list_schemas,
    remove_schema,
)


def _vault(tmp_path: Path) -> Path:
    init(tmp_path)
    return tmp_path


# --- add_schema: happy paths -------------------------------------------------


def test_add_schema_returns_schema_and_persists(tmp_path: Path) -> None:
    root = _vault(tmp_path)

    result = add_schema(root, "person", ["employer", "role"])

    assert result == Schema(name="person", fields=["employer", "role"])
    assert (VaultLayout(root).entities_dir / "person").is_dir()
    assert [s.name for s in list_schemas(root)] == ["person"]


def test_add_schema_zero_fields_allowed(tmp_path: Path) -> None:
    root = _vault(tmp_path)

    result = add_schema(root, "note", [])

    assert result == Schema(name="note", fields=[])


# --- add_schema: validation branches ----------------------------------------


@pytest.mark.parametrize(
    "bad_name",
    ["Person", "with space", "with/slash", "", "-", "café"],
)
def test_add_schema_invalid_slug(tmp_path: Path, bad_name: str) -> None:
    root = _vault(tmp_path)

    with pytest.raises(InvalidSchemaError):
        add_schema(root, bad_name, [])


def test_add_schema_duplicate_schema(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    add_schema(root, "person", ["role"])

    with pytest.raises(SchemaExistsError):
        add_schema(root, "person", ["employer"])

    # Existing schema is untouched.
    assert list_schemas(root)[0].fields == ["role"]


@pytest.mark.parametrize("reserved", ["name", "aliases"])
def test_add_schema_reserved_field(tmp_path: Path, reserved: str) -> None:
    root = _vault(tmp_path)

    with pytest.raises(InvalidSchemaError):
        add_schema(root, "person", [reserved])

    assert list_schemas(root) == []


def test_add_schema_duplicate_field(tmp_path: Path) -> None:
    root = _vault(tmp_path)

    with pytest.raises(InvalidSchemaError):
        add_schema(root, "person", ["role", "role"])


@pytest.mark.parametrize("bad_field", ["", "   "])
def test_add_schema_empty_field_name(tmp_path: Path, bad_field: str) -> None:
    root = _vault(tmp_path)

    with pytest.raises(InvalidSchemaError):
        add_schema(root, "person", [bad_field])


def test_add_schema_validates_before_write(tmp_path: Path) -> None:
    root = _vault(tmp_path)

    with pytest.raises(InvalidSchemaError):
        add_schema(root, "person", ["name"])

    # No partial write: neither DB row nor folder created.
    assert list_schemas(root) == []
    assert not (VaultLayout(root).entities_dir / "person").exists()


# --- list_schemas ------------------------------------------------------------


def test_list_schemas_empty(tmp_path: Path) -> None:
    root = _vault(tmp_path)

    assert list_schemas(root) == []


def test_list_schemas_ordered_by_name(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    add_schema(root, "person", ["role"])
    add_schema(root, "company", ["industry"])

    assert [s.name for s in list_schemas(root)] == ["company", "person"]


# --- remove_schema -----------------------------------------------------------


def test_remove_schema_happy_path(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    add_schema(root, "person", ["role"])

    remove_schema(root, "person")

    assert list_schemas(root) == []
    assert not (VaultLayout(root).entities_dir / "person").exists()


def test_remove_schema_not_found(tmp_path: Path) -> None:
    root = _vault(tmp_path)

    with pytest.raises(SchemaNotFoundError):
        remove_schema(root, "nope")


def test_remove_schema_in_use(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    add_schema(root, "person", ["role"])

    # Entity-creation commands don't exist yet; insert a raw entities row to
    # exercise the in-use guard.
    db_path = VaultLayout(root).db_path
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO entities (schema, name) VALUES (?, ?)",
            ("person", "Alice"),
        )

    with pytest.raises(SchemaInUseError):
        remove_schema(root, "person")

    # Nothing removed.
    assert [s.name for s in list_schemas(root)] == ["person"]
    assert (VaultLayout(root).entities_dir / "person").is_dir()

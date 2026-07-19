"""Integration tests for the SQLite schema bootstrap."""

from __future__ import annotations

import sqlite3

import pytest

from forte.db.schema import initialize_database

EXPECTED_TABLES = {
    "documents",
    "schemas",
    "entities",
    "entity_field_values",
    "mentions",
    "ingest_changes",
}


def _tables(db_path):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def test_initialize_database_creates_all_mvp_tables(tmp_path):
    db_path = tmp_path / "index.db"

    initialize_database(db_path)

    assert db_path.exists()
    tables = _tables(db_path)
    assert EXPECTED_TABLES.issubset(tables)
    # entity_embeddings is explicitly deferred.
    assert "entity_embeddings" not in tables


def test_initialize_database_refuses_to_overwrite(tmp_path):
    db_path = tmp_path / "index.db"
    initialize_database(db_path)
    original_bytes = db_path.read_bytes()

    with pytest.raises(FileExistsError):
        initialize_database(db_path)

    # File must not have been modified.
    assert db_path.read_bytes() == original_bytes

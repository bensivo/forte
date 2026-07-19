"""SQLite schema bootstrap for a fresh Forte vault database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

# entity_embeddings table intentionally deferred until the embeddings decision lands.

_DDL: list[str] = [
    """
    CREATE TABLE documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_path TEXT,
        content_hash TEXT,
        raw_path TEXT,
        processed_path TEXT,
        ingested_at TEXT,
        status TEXT
    )
    """,
    """
    CREATE TABLE schemas (
        name TEXT PRIMARY KEY,
        fields_json TEXT
    )
    """,
    """
    CREATE TABLE entities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        schema TEXT,
        name TEXT,
        aliases_json TEXT,
        fields_json TEXT,
        file_path TEXT
    )
    """,
    """
    CREATE TABLE entity_field_values (
        entity_id INTEGER,
        field TEXT,
        value TEXT,
        source_doc_id INTEGER
    )
    """,
    """
    CREATE TABLE mentions (
        doc_id INTEGER,
        entity_id INTEGER,
        quote TEXT,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE ingest_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_id INTEGER,
        kind TEXT,
        payload_json TEXT,
        status TEXT
    )
    """,
]


def initialize_database(db_path: Path) -> None:
    """Create a fresh SQLite database with the MVP schema.

    Raises FileExistsError if the target path already exists.
    """
    if db_path.exists():
        raise FileExistsError(f"Database file already exists at {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        with conn:
            for stmt in _DDL:
                conn.execute(stmt)
    finally:
        conn.close()

"""SQLite schema bootstrap for a fresh Forte vault database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Vector storage decision (resolves the prior "entity_embeddings deferred" note):
# at this vault's modest scale (hundreds-low-thousands of chunks) we store each embedding
# as a plain BLOB of float32 bytes on the `chunks` row and do brute-force cosine similarity
# in Python at query time, rather than adding a sqlite-vec dependency. The chosen embedding
# model (sentence-transformers/all-MiniLM-L6-v2) produces 384-dim vectors; the BLOB column
# doesn't need a fixed width in DDL. If corpus size grows enough that brute-force scan is
# too slow, swap in sqlite-vec (or another ANN index) behind the same read/write helpers.

_DDL: list[str] = [
    """
    CREATE TABLE documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
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
    """
    CREATE TABLE chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_type TEXT,
        source_id INTEGER,
        chunk_index INTEGER,
        text TEXT,
        embedding BLOB,
        model TEXT
    )
    """,
    """
    CREATE VIRTUAL TABLE chunks_fts USING fts5(
        text,
        chunk_id UNINDEXED
    )
    """,
    """
    CREATE TABLE index_state (
        key TEXT PRIMARY KEY,
        value TEXT
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

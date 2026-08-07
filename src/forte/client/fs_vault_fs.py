"""Local filesystem and SQLite implementation of the vault filesystem interface."""

from __future__ import annotations

from pathlib import Path

import sqlite3

from forte.interface.vault_fs import IVaultFs

# Starter contents of a new vault's `forte.yaml`. The API key is written as a
# `${VAR}` reference so a committed config never contains a raw secret.
_DEFAULT_CONFIG_CONTENT = (
    "# Forte vault config.\n"
    "model:\n"
    "  extraction: claude-haiku-4-5\n"
    "api_keys:\n"
    "  anthropic: ${ANTHROPIC_API_KEY}\n"
    "# editor: vim\n"
)

# DDL for a fresh vault index. The entity_embeddings table is intentionally
# deferred until the embeddings decision lands.
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
]


class LocalVaultFs(IVaultFs):
    """Concrete IVaultFs implementation backed by the local filesystem and SQLite.

    Uses the standard library `pathlib` for filesystem checks and directory
    creation, writes the starter `forte.yaml`, and bootstraps a fresh SQLite
    index with the MVP schema.
    """

    def exists(self, path: Path) -> bool:
        """Check whether a path exists on the local filesystem.

        Args:
            path (Path): The path to check.

        Returns:
            (bool) True if the path exists, False otherwise.
        """
        return path.exists()

    def make_dirs(self, path: Path) -> None:
        """Create a directory, including any missing parent directories.

        Fails loudly if any part of the path already exists.

        Args:
            path (Path): The directory path to create.

        Returns:
            None

        Raises:
            FileExistsError: if `path` (or a parent) already exists.
        """
        path.mkdir(parents=True)

    def write_default_config(self, path: Path) -> None:
        """Write the default Forte config file to `path`.

        Args:
            path (Path): The destination path for the config file.

        Returns:
            None

        Raises:
            FileExistsError: if `path` already exists.
        """
        if path.exists():
            raise FileExistsError(f"Config file already exists: {path}")
        path.write_text(_DEFAULT_CONFIG_CONTENT, encoding="utf-8")

    def init_db(self, path: Path) -> None:
        """Create a fresh SQLite database with the MVP schema at `path`.

        Args:
            path (Path): The destination path for the SQLite database file.

        Returns:
            None

        Raises:
            FileExistsError: if `path` already exists.
        """
        if path.exists():
            raise FileExistsError(f"Database file already exists at {path}")

        conn = sqlite3.connect(path)
        try:
            with conn:
                for stmt in _DDL:
                    conn.execute(stmt)
        finally:
            conn.close()

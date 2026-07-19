"""DB layer: persistence for :class:`Schema` over an existing vault.

Dual-writes each schema to the SQLite ``schemas`` table and to a matching
``entities/<name>/`` folder. The ``schemas`` table itself is created by the
``forte init`` bootstrap (see ``db/schema.py``); this module only reads/writes it.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from forte.domain.schema import Schema
from forte.domain.vault import VaultLayout


class SchemaRepository:
    """Read/write access to schemas stored in a vault rooted at ``root``."""

    def __init__(self, root: Path) -> None:
        self._layout = VaultLayout(root)

    def _folder(self, name: str) -> Path:
        return self._layout.entities_dir / name

    def add(self, schema: Schema) -> None:
        """Insert the schema row and create its ``entities/<name>/`` folder."""
        folder = self._folder(schema.name)
        fields_json = json.dumps(list(schema.fields))

        conn = sqlite3.connect(self._layout.db_path)
        try:
            with conn:
                conn.execute(
                    "INSERT INTO schemas (name, fields_json) VALUES (?, ?)",
                    (schema.name, fields_json),
                )
                # mkdir without exist_ok so an unexpected pre-existing folder
                # surfaces as an error rather than being silently reused.
                folder.mkdir(parents=True)
        finally:
            conn.close()

    def list(self) -> list[Schema]:
        """Return every schema, preserving each schema's field order."""
        conn = sqlite3.connect(self._layout.db_path)
        try:
            rows = conn.execute(
                "SELECT name, fields_json FROM schemas ORDER BY name"
            ).fetchall()
        finally:
            conn.close()
        return [self._row_to_schema(name, fields_json) for name, fields_json in rows]

    def get(self, name: str) -> Schema | None:
        """Return a single schema by name, or ``None`` if it does not exist."""
        conn = sqlite3.connect(self._layout.db_path)
        try:
            row = conn.execute(
                "SELECT name, fields_json FROM schemas WHERE name = ?",
                (name,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return self._row_to_schema(row[0], row[1])

    def remove(self, name: str) -> None:
        """Delete the schema row and remove its (empty) ``entities/<name>/`` folder."""
        folder = self._folder(name)

        conn = sqlite3.connect(self._layout.db_path)
        try:
            with conn:
                conn.execute("DELETE FROM schemas WHERE name = ?", (name,))
                if folder.exists():
                    # rmdir refuses a non-empty directory: fail loudly rather
                    # than recursively deleting entities the caller missed.
                    folder.rmdir()
        finally:
            conn.close()

    def exists(self, name: str) -> bool:
        """Return whether a schema with the given name is defined."""
        conn = sqlite3.connect(self._layout.db_path)
        try:
            row = conn.execute(
                "SELECT 1 FROM schemas WHERE name = ?",
                (name,),
            ).fetchone()
        finally:
            conn.close()
        return row is not None

    @staticmethod
    def _row_to_schema(name: str, fields_json: str | None) -> Schema:
        fields = json.loads(fields_json) if fields_json else []
        return Schema(name=name, fields=list(fields))

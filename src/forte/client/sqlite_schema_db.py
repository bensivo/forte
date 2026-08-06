import json
import sqlite3
from pathlib import Path

from forte.interface.schema_db import ISchemaDb
from forte.model.schema import Schema, SchemaField
from forte.model.vault import VaultLayout
from forte.services.discovery import find_vault_root


class SqliteSchemaDb(ISchemaDb):
    """
    SQLite implementation of ISchemaDb. Dual-writes each schema to the
    ``schemas`` table and to a matching ``entities/<name>/`` folder in the
    vault. The ``schemas`` table itself is created by the ``forte init``
    bootstrap; this client only reads/writes it.

    Resolves the vault root (and opens a fresh connection) from the current
    working directory on every call, so it can be constructed unconditionally
    at wiring time — callers only see a `VaultNotFoundError` when a method
    that actually needs a vault is invoked outside of one.
    """

    def _layout(self) -> VaultLayout:
        root = find_vault_root(Path.cwd())
        return VaultLayout(root)

    def _folder(self, layout: VaultLayout, name: str) -> Path:
        return layout.entities_dir / name

    def check_exists(self, name: str) -> bool:
        layout = self._layout()
        conn = sqlite3.connect(layout.db_path)
        try:
            row = conn.execute(
                "SELECT 1 FROM schemas WHERE name = ?",
                (name,),
            ).fetchone()
        finally:
            conn.close()
        return row is not None

    def add(self, schema: Schema) -> None:
        layout = self._layout()
        folder = self._folder(layout, schema.name)
        fields_json = json.dumps([f.name for f in schema.fields])

        conn = sqlite3.connect(layout.db_path)
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

    def get(self, name: str) -> Schema | None:
        layout = self._layout()
        conn = sqlite3.connect(layout.db_path)
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

    def list(self) -> list[Schema]:
        layout = self._layout()
        conn = sqlite3.connect(layout.db_path)
        try:
            rows = conn.execute(
                "SELECT name, fields_json FROM schemas ORDER BY name"
            ).fetchall()
        finally:
            conn.close()
        return [self._row_to_schema(name, fields_json) for name, fields_json in rows]

    def remove(self, name: str) -> None:
        layout = self._layout()
        folder = self._folder(layout, name)

        conn = sqlite3.connect(layout.db_path)
        try:
            with conn:
                conn.execute("DELETE FROM schemas WHERE name = ?", (name,))
                if folder.exists():
                    # rmdir refuses a non-empty directory: fail loudly rather
                    # than recursively deleting entities the caller missed.
                    folder.rmdir()
        finally:
            conn.close()

    def count_entities(self, name: str) -> int:
        layout = self._layout()
        conn = sqlite3.connect(layout.db_path)
        try:
            (count,) = conn.execute(
                "SELECT COUNT(*) FROM entities WHERE schema = ?",
                (name,),
            ).fetchone()
        finally:
            conn.close()
        return count

    @staticmethod
    def _row_to_schema(name: str, fields_json: str | None) -> Schema:
        field_names = json.loads(fields_json) if fields_json else []
        return Schema(name=name, fields=[SchemaField(name=n) for n in field_names])

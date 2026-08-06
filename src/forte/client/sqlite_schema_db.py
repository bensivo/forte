import json
import sqlite3
from pathlib import Path

from forte.domain.vault import VaultLayout
from forte.interface.schema_db import ISchemaDb
from forte.model.schema import Schema, SchemaField


class SqliteSchemaDb(ISchemaDb):
    """
    SQLite implementation of ISchemaDb. Dual-writes each schema to the
    ``schemas`` table and to a matching ``entities/<name>/`` folder in the
    vault. The ``schemas`` table itself is created by the ``forte init``
    bootstrap; this client only reads/writes it.
    """

    def __init__(self, conn: sqlite3.Connection, root: Path):
        """
        Args:
            conn (sqlite3.Connection): Open connection to the vault's index db.
            root (Path): Root directory of the vault, used to locate the
                ``entities/<name>/`` folder for each schema.
        """
        self._conn = conn
        self._layout = VaultLayout(root)

    def _folder(self, name: str) -> Path:
        return self._layout.entities_dir / name

    def check_exists(self, name: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM schemas WHERE name = ?",
            (name,),
        ).fetchone()
        return row is not None

    def add(self, schema: Schema) -> None:
        folder = self._folder(schema.name)
        fields_json = json.dumps([f.name for f in schema.fields])

        with self._conn:
            self._conn.execute(
                "INSERT INTO schemas (name, fields_json) VALUES (?, ?)",
                (schema.name, fields_json),
            )
            # mkdir without exist_ok so an unexpected pre-existing folder
            # surfaces as an error rather than being silently reused.
            folder.mkdir(parents=True)

    def list(self) -> list[Schema]:
        rows = self._conn.execute(
            "SELECT name, fields_json FROM schemas ORDER BY name"
        ).fetchall()
        return [self._row_to_schema(name, fields_json) for name, fields_json in rows]

    def remove(self, name: str) -> None:
        folder = self._folder(name)

        with self._conn:
            self._conn.execute("DELETE FROM schemas WHERE name = ?", (name,))
            if folder.exists():
                # rmdir refuses a non-empty directory: fail loudly rather
                # than recursively deleting entities the caller missed.
                folder.rmdir()

    def count_entities(self, name: str) -> int:
        (count,) = self._conn.execute(
            "SELECT COUNT(*) FROM entities WHERE schema = ?",
            (name,),
        ).fetchone()
        return count

    @staticmethod
    def _row_to_schema(name: str, fields_json: str | None) -> Schema:
        field_names = json.loads(fields_json) if fields_json else []
        return Schema(name=name, fields=[SchemaField(name=n) for n in field_names])


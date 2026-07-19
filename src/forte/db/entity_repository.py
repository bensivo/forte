"""DB layer: persistence for :class:`Entity` over an existing vault.

Entities are part of the human-readable knowledge base, so every write
*dual-writes*: a markdown file at ``entities/<schema>/<slug>.md`` (YAML
frontmatter + free-form body) AND a row in the SQLite ``entities`` table. Both
writes happen together in each method so the two stores can't drift within an
operation. The ``entities`` table itself is created by the ``forte init``
bootstrap (see ``db/schema.py``); this module only reads/writes it.

Aliases and fields are stored as JSON in the DB (``aliases_json`` /
``fields_json``) and as YAML frontmatter on disk (via the serializer in
``domain/entity_markdown``). ``file_path`` is stored vault-relative so vaults
stay portable.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from forte.domain.entity import Entity
from forte.domain.entity_markdown import slugify, to_markdown
from forte.domain.vault import VaultLayout


class EntityRepository:
    """Read/write access to entities stored in a vault rooted at ``root``."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._layout = VaultLayout(root)

    def _schema_dir(self, schema: str) -> Path:
        return self._layout.entities_dir / schema

    def _abs_path(self, rel_path: str) -> Path:
        return self._root / rel_path

    def _rel_path(self, path: Path) -> str:
        return str(path.relative_to(self._root))

    def _resolve_path(self, schema: str, slug: str, entity_id: int) -> Path:
        """Pick the on-disk path for an entity, disambiguating collisions.

        Normally ``<schema>/<slug>.md``; if that file already exists for a
        *different* entity, append the id to keep names unique rather than
        overwriting the other entity's file.
        """
        folder = self._schema_dir(schema)
        preferred = folder / f"{slug}.md"
        if not preferred.exists():
            return preferred
        return folder / f"{slug}-{entity_id}.md"

    def add(self, entity: Entity) -> Entity:
        """Insert the ``entities`` row and write the markdown file together.

        Assigns the SQLite auto-increment id, writes the markdown at
        ``entities/<schema>/<slug>.md`` (disambiguating filename collisions),
        and returns the entity with its new ``id`` and vault-relative
        ``file_path`` populated.
        """
        folder = self._schema_dir(entity.schema)
        if not folder.is_dir():
            raise FileNotFoundError(
                f"entities folder for schema '{entity.schema}' does not exist "
                f"({folder}); add the schema before adding entities to it"
            )

        aliases_json = json.dumps(list(entity.aliases))
        fields_json = json.dumps(dict(entity.fields))

        conn = sqlite3.connect(self._layout.db_path)
        try:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO entities "
                    "(schema, name, aliases_json, fields_json, file_path) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (entity.schema, entity.name, aliases_json, fields_json, None),
                )
                entity_id = cursor.lastrowid

                slug = slugify(entity.name)
                path = self._resolve_path(entity.schema, slug, entity_id)
                rel_path = self._rel_path(path)

                stored = Entity(
                    schema=entity.schema,
                    name=entity.name,
                    aliases=list(entity.aliases),
                    fields=dict(entity.fields),
                    body=entity.body,
                    id=entity_id,
                    file_path=rel_path,
                )
                path.write_text(to_markdown(stored), encoding="utf-8")

                conn.execute(
                    "UPDATE entities SET file_path = ? WHERE id = ?",
                    (rel_path, entity_id),
                )
        finally:
            conn.close()

        return stored

    def get(self, entity_id: int) -> Entity | None:
        """Return a single entity by id, or ``None`` if it does not exist."""
        conn = sqlite3.connect(self._layout.db_path)
        try:
            row = conn.execute(
                "SELECT id, schema, name, aliases_json, fields_json, file_path "
                "FROM entities WHERE id = ?",
                (entity_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return self._row_to_entity(row)

    def list(self, schema: str | None = None) -> list[Entity]:
        """Return all entities (or only those of ``schema``), ordered by id."""
        conn = sqlite3.connect(self._layout.db_path)
        try:
            if schema is None:
                rows = conn.execute(
                    "SELECT id, schema, name, aliases_json, fields_json, file_path "
                    "FROM entities ORDER BY id"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, schema, name, aliases_json, fields_json, file_path "
                    "FROM entities WHERE schema = ? ORDER BY id",
                    (schema,),
                ).fetchall()
        finally:
            conn.close()
        return [self._row_to_entity(row) for row in rows]

    def update(self, entity: Entity) -> None:
        """Rewrite the markdown file and row for an existing entity.

        If the name (and therefore slug) changed, the file is renamed and
        ``file_path`` updated; the old file is not left behind.
        """
        if entity.id is None:
            raise ValueError("cannot update an entity without an id")

        folder = self._schema_dir(entity.schema)
        if not folder.is_dir():
            raise FileNotFoundError(
                f"entities folder for schema '{entity.schema}' does not exist "
                f"({folder})"
            )

        aliases_json = json.dumps(list(entity.aliases))
        fields_json = json.dumps(dict(entity.fields))

        conn = sqlite3.connect(self._layout.db_path)
        try:
            row = conn.execute(
                "SELECT file_path FROM entities WHERE id = ?",
                (entity.id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"entity #{entity.id} does not exist")
            old_rel_path = row[0]

            slug = slugify(entity.name)
            new_path = self._resolve_path(entity.schema, slug, entity.id)
            # _resolve_path skips paths that already exist; if the only clashing
            # file is this entity's own current file, keep using it.
            if old_rel_path is not None and self._abs_path(old_rel_path) == folder / f"{slug}.md":
                new_path = folder / f"{slug}.md"
            new_rel_path = self._rel_path(new_path)

            stored = Entity(
                schema=entity.schema,
                name=entity.name,
                aliases=list(entity.aliases),
                fields=dict(entity.fields),
                body=entity.body,
                id=entity.id,
                file_path=new_rel_path,
            )

            with conn:
                conn.execute(
                    "UPDATE entities "
                    "SET schema = ?, name = ?, aliases_json = ?, "
                    "fields_json = ?, file_path = ? WHERE id = ?",
                    (
                        entity.schema,
                        entity.name,
                        aliases_json,
                        fields_json,
                        new_rel_path,
                        entity.id,
                    ),
                )
                new_path.write_text(to_markdown(stored), encoding="utf-8")
                if old_rel_path is not None:
                    old_path = self._abs_path(old_rel_path)
                    if old_path != new_path and old_path.exists():
                        old_path.unlink()
        finally:
            conn.close()

    def remove(self, entity_id: int) -> None:
        """Delete the markdown file and the ``entities`` row together."""
        conn = sqlite3.connect(self._layout.db_path)
        try:
            row = conn.execute(
                "SELECT file_path FROM entities WHERE id = ?",
                (entity_id,),
            ).fetchone()
            with conn:
                conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
                if row is not None and row[0] is not None:
                    path = self._abs_path(row[0])
                    if path.exists():
                        path.unlink()
        finally:
            conn.close()

    @staticmethod
    def _row_to_entity(row: tuple) -> Entity:
        entity_id, schema, name, aliases_json, fields_json, file_path = row
        aliases = json.loads(aliases_json) if aliases_json else []
        fields = json.loads(fields_json) if fields_json else {}
        return Entity(
            schema=schema,
            name=name,
            aliases=list(aliases),
            fields=dict(fields),
            body="",
            id=entity_id,
            file_path=file_path,
        )

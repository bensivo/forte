import json
import re
import sqlite3
from pathlib import Path

import yaml

from forte.interface.entity_db import IEntityDb
from forte.model.entity import Entity
from forte.model.vault import VaultLayout
from forte.services.discovery import find_vault_root

_NAME_KEY = "name"
_ALIASES_KEY = "aliases"
_FRONTMATTER_DELIM = "---"


class SqliteEntityDb(IEntityDb):
    """
    SQLite implementation of IEntityDb. Entities are part of the
    human-readable knowledge base, so every write *dual-writes*: a markdown
    file at ``entities/<schema>/<slug>.md`` (YAML frontmatter + free-form
    body) AND a row in the SQLite ``entities`` table. Both writes happen
    together in each method so the two stores can't drift within an
    operation. The ``entities`` table itself is created by the ``forte init``
    bootstrap; this client only reads/writes it.

    Resolves the vault root (and opens a fresh connection) from the current
    working directory on every call, so it can be constructed unconditionally
    at wiring time — callers only see a `VaultNotFoundError` when a method
    that actually needs a vault is invoked outside of one.
    """

    def _layout(self) -> VaultLayout:
        root = find_vault_root(Path.cwd())
        return VaultLayout(root)

    def _schema_dir(self, layout: VaultLayout, schema: str) -> Path:
        return layout.entities_dir / schema

    def _abs_path(self, layout: VaultLayout, rel_path: str) -> Path:
        return layout.root / rel_path

    def _rel_path(self, layout: VaultLayout, path: Path) -> str:
        return str(path.relative_to(layout.root))

    def _resolve_path(self, layout: VaultLayout, schema: str, slug: str, entity_id: int) -> Path:
        """Pick the on-disk path for an entity, disambiguating collisions.

        Normally ``<schema>/<slug>.md``; if that file already exists for a
        *different* entity, append the id to keep names unique rather than
        overwriting the other entity's file.
        """
        folder = self._schema_dir(layout, schema)
        preferred = folder / f"{slug}.md"
        if not preferred.exists():
            return preferred
        return folder / f"{slug}-{entity_id}.md"

    def add(self, entity: Entity) -> Entity:
        layout = self._layout()
        folder = self._schema_dir(layout, entity.schema)
        if not folder.is_dir():
            raise FileNotFoundError(
                f"entities folder for schema '{entity.schema}' does not exist "
                f"({folder}); add the schema before adding entities to it"
            )

        aliases_json = json.dumps(list(entity.aliases))
        fields_json = json.dumps(dict(entity.fields))

        conn = sqlite3.connect(layout.db_path)
        try:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO entities "
                    "(schema, name, aliases_json, fields_json, file_path) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (entity.schema, entity.name, aliases_json, fields_json, None),
                )
                entity_id = cursor.lastrowid

                slug = self._slugify(entity.name)
                path = self._resolve_path(layout, entity.schema, slug, entity_id)
                rel_path = self._rel_path(layout, path)

                stored = Entity(
                    schema=entity.schema,
                    name=entity.name,
                    aliases=list(entity.aliases),
                    fields=dict(entity.fields),
                    body=entity.body,
                    id=entity_id,
                    file_path=rel_path,
                )
                path.write_text(self._to_markdown(stored), encoding="utf-8")

                conn.execute(
                    "UPDATE entities SET file_path = ? WHERE id = ?",
                    (rel_path, entity_id),
                )
        finally:
            conn.close()

        return stored

    def get(self, entity_id: int) -> Entity | None:
        layout = self._layout()
        conn = sqlite3.connect(layout.db_path)
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
        layout = self._layout()
        conn = sqlite3.connect(layout.db_path)
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
        if entity.id is None:
            raise ValueError("cannot update an entity without an id")

        layout = self._layout()
        folder = self._schema_dir(layout, entity.schema)
        if not folder.is_dir():
            raise FileNotFoundError(
                f"entities folder for schema '{entity.schema}' does not exist "
                f"({folder})"
            )

        aliases_json = json.dumps(list(entity.aliases))
        fields_json = json.dumps(dict(entity.fields))

        conn = sqlite3.connect(layout.db_path)
        try:
            row = conn.execute(
                "SELECT file_path FROM entities WHERE id = ?",
                (entity.id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"entity #{entity.id} does not exist")
            old_rel_path = row[0]

            slug = self._slugify(entity.name)
            new_path = self._resolve_path(layout, entity.schema, slug, entity.id)
            # _resolve_path skips paths that already exist; if the only clashing
            # file is this entity's own current file, keep using it.
            if (
                old_rel_path is not None
                and self._abs_path(layout, old_rel_path) == folder / f"{slug}.md"
            ):
                new_path = folder / f"{slug}.md"
            new_rel_path = self._rel_path(layout, new_path)

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
                new_path.write_text(self._to_markdown(stored), encoding="utf-8")
                if old_rel_path is not None:
                    old_path = self._abs_path(layout, old_rel_path)
                    if old_path != new_path and old_path.exists():
                        old_path.unlink()
        finally:
            conn.close()

    def remove(self, entity_id: int) -> None:
        layout = self._layout()
        conn = sqlite3.connect(layout.db_path)
        try:
            row = conn.execute(
                "SELECT file_path FROM entities WHERE id = ?",
                (entity_id,),
            ).fetchone()
            with conn:
                conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
                if row is not None and row[0] is not None:
                    path = self._abs_path(layout, row[0])
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

    @staticmethod
    def _slugify(name: str) -> str:
        """Turn a canonical entity name into an on-disk filename slug."""
        slug = name.strip().lower()
        slug = re.sub(r"\s+", "-", slug)
        # Keep only URL/file-safe characters; drop everything else.
        slug = re.sub(r"[^a-z0-9_-]", "", slug)
        slug = re.sub(r"-{2,}", "-", slug).strip("-")
        return slug

    @staticmethod
    def _to_markdown(entity: Entity) -> str:
        """Render an entity as a YAML-frontmatter markdown document."""
        front: dict[str, object] = {
            _NAME_KEY: entity.name,
            _ALIASES_KEY: list(entity.aliases),
        }
        for key, value in entity.fields.items():
            front[key] = "" if value is None else value

        frontmatter = yaml.safe_dump(
            front,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )

        body = entity.body.strip()
        if body:
            return f"{_FRONTMATTER_DELIM}\n{frontmatter}{_FRONTMATTER_DELIM}\n\n{body}\n"
        return f"{_FRONTMATTER_DELIM}\n{frontmatter}{_FRONTMATTER_DELIM}\n"

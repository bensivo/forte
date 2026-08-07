"""Shared wiring for the ported agent-pipeline integration tests.

Builds the new 3-layer stack (services over the SQLite/filesystem clients)
against a throwaway vault, with the vault registry pointed at a temp home
directory so tests never read or write the real ``~/.forte/``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from forte.client.fs_vault_fs import LocalVaultFs
from forte.client.sqlite_document_db import SqliteDocumentDb
from forte.client.sqlite_entity_db import SqliteEntityDb
from forte.client.sqlite_mention_db import SqliteMentionDb
from forte.client.sqlite_schema_db import SqliteSchemaDb
from forte.client.yaml_vault_registry import YamlVaultRegistry
from forte.model.vault import VaultContext
from forte.service.document_service import DocumentService
from forte.service.entity_service import EntityService
from forte.service.schema_service import SchemaService
from forte.service.vault_service import VaultService


@dataclass
class Stack:
    """One wired-up vault plus the services that operate on it."""

    root: Path
    context: VaultContext
    document_service: DocumentService
    entity_service: EntityService
    schema_service: SchemaService


def build_stack(tmp_path: Path) -> Stack:
    """Create a vault under ``tmp_path`` and wire the services against it."""
    root = tmp_path / "vault"
    home_dir = tmp_path / "home"
    home_dir.mkdir(parents=True, exist_ok=True)

    vault_service = VaultService(YamlVaultRegistry(home_dir=home_dir), LocalVaultFs())
    vault = vault_service.create_vault("test", root)

    context = VaultContext()
    context.set_root(vault.path)

    schema_db = SqliteSchemaDb(context)
    entity_db = SqliteEntityDb(context)
    document_db = SqliteDocumentDb(context)
    mention_db = SqliteMentionDb(context)

    return Stack(
        root=vault.path,
        context=context,
        document_service=DocumentService(document_db, mention_db, entity_db),
        entity_service=EntityService(entity_db, schema_db),
        schema_service=SchemaService(schema_db),
    )


def mentions_for_entity(root: Path, entity_id: int) -> list[tuple[int, str]]:
    """Return ``(doc_id, quote)`` for every mention row of ``entity_id``."""
    conn = sqlite3.connect(root / "forte.db")
    try:
        rows = conn.execute(
            "SELECT doc_id, quote FROM mentions WHERE entity_id = ? ORDER BY rowid",
            (entity_id,),
        ).fetchall()
    finally:
        conn.close()
    return [(row[0], row[1]) for row in rows]


def mentions_for_doc(root: Path, doc_id: int) -> list[tuple[int, str]]:
    """Return ``(entity_id, quote)`` for every mention row of ``doc_id``."""
    conn = sqlite3.connect(root / "forte.db")
    try:
        rows = conn.execute(
            "SELECT entity_id, quote FROM mentions WHERE doc_id = ? ORDER BY rowid",
            (doc_id,),
        ).fetchall()
    finally:
        conn.close()
    return [(row[0], row[1]) for row in rows]

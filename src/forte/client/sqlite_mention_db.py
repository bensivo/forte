import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from forte.interface.mention_db import IMentionDb
from forte.model.vault import VaultLayout
from forte.services.discovery import find_vault_root


class SqliteMentionDb(IMentionDb):
    """
    SQLite implementation of IMentionDb. Mentions are pure DB rows in the
    ``mentions`` table (created by the ``forte init`` bootstrap); there is no
    markdown counterpart to dual-write. This client only reads/writes that
    table.

    Resolves the vault root (and opens a fresh connection) from the current
    working directory on every call, so it can be constructed unconditionally
    at wiring time — callers only see a `VaultNotFoundError` when a method
    that actually needs a vault is invoked outside of one.
    """

    def _layout(self) -> VaultLayout:
        root = find_vault_root(Path.cwd())
        return VaultLayout(root)

    def exists(self, doc_id: int, entity_id: int) -> bool:
        layout = self._layout()
        conn = sqlite3.connect(layout.db_path)
        try:
            row = conn.execute(
                "SELECT 1 FROM mentions WHERE doc_id = ? AND entity_id = ? LIMIT 1",
                (doc_id, entity_id),
            ).fetchone()
        finally:
            conn.close()
        return row is not None

    def add(self, doc_id: int, entity_id: int, quote: str = "") -> None:
        layout = self._layout()
        created_at = datetime.now(UTC).isoformat()
        conn = sqlite3.connect(layout.db_path)
        try:
            with conn:
                conn.execute(
                    "INSERT INTO mentions (doc_id, entity_id, quote, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (doc_id, entity_id, quote, created_at),
                )
        finally:
            conn.close()

    def remove(self, doc_id: int, entity_id: int) -> None:
        layout = self._layout()
        conn = sqlite3.connect(layout.db_path)
        try:
            with conn:
                conn.execute(
                    "DELETE FROM mentions WHERE doc_id = ? AND entity_id = ?",
                    (doc_id, entity_id),
                )
        finally:
            conn.close()

    def remove_for_doc(self, doc_id: int) -> None:
        layout = self._layout()
        conn = sqlite3.connect(layout.db_path)
        try:
            with conn:
                conn.execute(
                    "DELETE FROM mentions WHERE doc_id = ?",
                    (doc_id,),
                )
        finally:
            conn.close()

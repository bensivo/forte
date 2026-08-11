import sqlite3
from datetime import UTC, datetime

from forte.interface.mention_db import IMentionDb
from forte.model.mention import Mention
from forte.model.vault import VaultContext, VaultLayout


class SqliteMentionDb(IMentionDb):
    """
    SQLite implementation of IMentionDb. Mentions are pure DB rows in the
    ``mentions`` table (created by the ``forte init`` bootstrap); there is no
    markdown counterpart to dual-write. This client only reads/writes that
    table.

    Resolves the vault root (and opens a fresh connection) from the injected
    `VaultContext` on every call, so it can be constructed unconditionally at
    wiring time, before the active vault is known — callers only see a
    `NoDefaultVaultError` when a method that actually needs a vault is
    invoked before one has been selected.
    """

    def __init__(self, context: VaultContext):
        """
        Args:
            context (VaultContext): Holds the active vault root, resolved
                lazily on each call.
        """
        self._context = context

    def _layout(self) -> VaultLayout:
        root = self._context.get_root()
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

    def list_for_doc(self, doc_id: int) -> list[Mention]:
        layout = self._layout()
        conn = sqlite3.connect(layout.db_path)
        try:
            rows = conn.execute(
                "SELECT doc_id, entity_id, quote, created_at FROM mentions "
                "WHERE doc_id = ? ORDER BY entity_id",
                (doc_id,),
            ).fetchall()
        finally:
            conn.close()
        return [
            Mention(doc_id=r[0], entity_id=r[1], quote=r[2] or "", created_at=r[3] or "")
            for r in rows
        ]

    def list_for_entity(self, entity_id: int) -> list[Mention]:
        layout = self._layout()
        conn = sqlite3.connect(layout.db_path)
        try:
            rows = conn.execute(
                "SELECT doc_id, entity_id, quote, created_at FROM mentions "
                "WHERE entity_id = ? ORDER BY doc_id",
                (entity_id,),
            ).fetchall()
        finally:
            conn.close()
        return [
            Mention(doc_id=r[0], entity_id=r[1], quote=r[2] or "", created_at=r[3] or "")
            for r in rows
        ]

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

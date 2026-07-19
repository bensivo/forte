"""DB layer: persistence for :class:`Mention` (doc-entity link rows).

Mentions are pure DB rows in the ``mentions`` table (created by the
``forte init`` bootstrap, see ``db/schema.py``); there is no markdown
counterpart to dual-write. This module only reads/writes that table.

Existence-validation of ``doc_id``/``entity_id`` against the ``documents``/
``entities`` tables is the service layer's responsibility, not this repo's.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from forte.domain.mention import Mention
from forte.domain.vault import VaultLayout


class MentionRepository:
    """Read/write access to mentions stored in a vault rooted at ``root``."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._layout = VaultLayout(root)

    def add(self, doc_id: int, entity_id: int, quote: str = "") -> None:
        """Insert a mention row with a current UTC ISO-8601 ``created_at``."""
        created_at = datetime.now(UTC).isoformat()
        conn = sqlite3.connect(self._layout.db_path)
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
        """Delete matching mention row(s); safe no-op if none match."""
        conn = sqlite3.connect(self._layout.db_path)
        try:
            with conn:
                conn.execute(
                    "DELETE FROM mentions WHERE doc_id = ? AND entity_id = ?",
                    (doc_id, entity_id),
                )
        finally:
            conn.close()

    def list_for_doc(self, doc_id: int) -> list[Mention]:
        """Return all mentions for a given doc."""
        conn = sqlite3.connect(self._layout.db_path)
        try:
            rows = conn.execute(
                "SELECT doc_id, entity_id, quote, created_at FROM mentions "
                "WHERE doc_id = ?",
                (doc_id,),
            ).fetchall()
        finally:
            conn.close()
        return [
            Mention(doc_id=r[0], entity_id=r[1], quote=r[2], created_at=r[3])
            for r in rows
        ]

    def list_for_entity(self, entity_id: int) -> list[Mention]:
        """Return all mentions for a given entity."""
        conn = sqlite3.connect(self._layout.db_path)
        try:
            rows = conn.execute(
                "SELECT doc_id, entity_id, quote, created_at FROM mentions "
                "WHERE entity_id = ?",
                (entity_id,),
            ).fetchall()
        finally:
            conn.close()
        return [
            Mention(doc_id=r[0], entity_id=r[1], quote=r[2], created_at=r[3])
            for r in rows
        ]

    def exists(self, doc_id: int, entity_id: int) -> bool:
        """Return ``True`` if a mention row exists for the given pair."""
        conn = sqlite3.connect(self._layout.db_path)
        try:
            row = conn.execute(
                "SELECT 1 FROM mentions WHERE doc_id = ? AND entity_id = ? LIMIT 1",
                (doc_id, entity_id),
            ).fetchone()
        finally:
            conn.close()
        return row is not None

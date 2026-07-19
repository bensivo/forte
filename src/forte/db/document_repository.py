"""DB layer: persistence for :class:`Document` over an existing vault.

Documents are part of the human-readable knowledge base, so every write
*dual-writes*: a raw copy of the original file at ``docs/raw/<filename>``, a
processed markdown file at ``docs/processed/<id>.md`` (YAML frontmatter +
extracted text body), AND a row in the SQLite ``documents`` table. The
``documents`` table itself is created by the ``forte init`` bootstrap (see
``db/schema.py``); this module only reads/writes it.

``raw_path`` and ``processed_path`` are stored vault-relative so vaults stay
portable, matching the ``file_path`` convention used for entities.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from forte.domain.document import Document
from forte.domain.document_markdown import to_markdown
from forte.domain.vault import VaultLayout


class DocumentRepository:
    """Read/write access to documents stored in a vault rooted at ``root``."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._layout = VaultLayout(root)

    def _rel_path(self, path: Path) -> str:
        return str(path.relative_to(self._root))

    def _resolve_raw_path(self, filename: str) -> Path:
        """Pick the on-disk path for a raw copy, disambiguating collisions.

        Normally ``docs/raw/<filename>``; if that file already exists (e.g. a
        different source file with the same basename was ingested earlier),
        append a numeric suffix before the extension to keep names unique
        rather than overwriting the other document's raw copy.
        """
        folder = self._layout.docs_raw_dir
        preferred = folder / filename
        if not preferred.exists():
            return preferred

        stem = preferred.stem
        suffix = preferred.suffix
        n = 1
        while True:
            candidate = folder / f"{stem}-{n}{suffix}"
            if not candidate.exists():
                return candidate
            n += 1

    def add(
        self, source_path: Path, content_hash: str, extracted_text: str, name: str
    ) -> Document:
        """Copy the source file, write processed markdown, and insert the row.

        Copies ``source_path`` into ``docs/raw/<original-filename>``
        (disambiguating on filename collision), inserts the ``documents`` row,
        then writes the processed markdown into ``docs/processed/<id>.md``.

        The processed filename is keyed by the document's id, but the id is
        only assigned once the row is inserted. So this method does the
        insert first (to obtain ``lastrowid``), writes the processed file
        named by that id, then UPDATEs the row's ``processed_path`` — a
        genuine two-phase write forced by the id/filename dependency, unlike
        entities where the slug is known up front.
        """
        raw_path = self._resolve_raw_path(source_path.name)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, raw_path)
        raw_rel_path = self._rel_path(raw_path)

        ingested_at = _now_iso()
        status = "ingested"

        conn = sqlite3.connect(self._layout.db_path)
        try:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO documents "
                    "(name, source_path, content_hash, raw_path, processed_path, "
                    "ingested_at, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        name,
                        str(source_path),
                        content_hash,
                        raw_rel_path,
                        None,
                        ingested_at,
                        status,
                    ),
                )
                doc_id = cursor.lastrowid

                stored = Document(
                    name=name,
                    source_path=str(source_path),
                    content_hash=content_hash,
                    ingested_at=ingested_at,
                    status=status,
                    raw_path=raw_rel_path,
                    processed_path=None,
                    id=doc_id,
                )

                processed_path = self._layout.docs_processed_dir / f"{doc_id}.md"
                processed_path.parent.mkdir(parents=True, exist_ok=True)
                processed_rel_path = self._rel_path(processed_path)
                processed_path.write_text(
                    to_markdown(stored, extracted_text), encoding="utf-8"
                )

                stored.processed_path = processed_rel_path

                conn.execute(
                    "UPDATE documents SET processed_path = ? WHERE id = ?",
                    (processed_rel_path, doc_id),
                )
        finally:
            conn.close()

        return stored

    def get(self, id: int) -> Document | None:
        """Return a single document by id, or ``None`` if it does not exist."""
        conn = sqlite3.connect(self._layout.db_path)
        try:
            row = conn.execute(
                "SELECT id, name, source_path, content_hash, raw_path, processed_path, "
                "ingested_at, status FROM documents WHERE id = ?",
                (id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return self._row_to_document(row)

    def list(self) -> list[Document]:
        """Return all documents, ordered by id."""
        conn = sqlite3.connect(self._layout.db_path)
        try:
            rows = conn.execute(
                "SELECT id, name, source_path, content_hash, raw_path, processed_path, "
                "ingested_at, status FROM documents ORDER BY id"
            ).fetchall()
        finally:
            conn.close()
        return [self._row_to_document(row) for row in rows]

    def find_by_identity(self, source_path: str, content_hash: str) -> Document | None:
        """Return the document with a matching ``source_path``/``content_hash``.

        Used by the service layer to detect a no-op re-ingest of an unchanged
        file. Returns ``None`` if no prior document matches both fields.
        """
        conn = sqlite3.connect(self._layout.db_path)
        try:
            row = conn.execute(
                "SELECT id, name, source_path, content_hash, raw_path, processed_path, "
                "ingested_at, status FROM documents "
                "WHERE source_path = ? AND content_hash = ? ORDER BY id LIMIT 1",
                (source_path, content_hash),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return self._row_to_document(row)

    @staticmethod
    def _row_to_document(row: tuple) -> Document:
        (
            doc_id,
            name,
            source_path,
            content_hash,
            raw_path,
            processed_path,
            ingested_at,
            status,
        ) = row
        return Document(
            name=name,
            source_path=source_path,
            content_hash=content_hash,
            ingested_at=ingested_at,
            status=status,
            raw_path=raw_path,
            processed_path=processed_path,
            id=doc_id,
        )


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from forte.interface.document_db import IDocumentDb
from forte.model.document import Document
from forte.model.document_markdown import to_markdown
from forte.model.vault import VaultContext, VaultLayout


class SqliteDocumentDb(IDocumentDb):
    """
    SQLite implementation of IDocumentDb. Documents are not dual-written as
    structured, editable knowledge like entities — each write instead
    produces two on-disk artifacts (an immutable raw copy under
    ``docs/raw/`` and a derived processed markdown copy under
    ``docs/processed/``) plus one row in the SQLite ``documents`` table. The
    ``documents`` table itself is created by the ``forte init`` bootstrap;
    this client only reads/writes it.

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

    def _rel_path(self, layout: VaultLayout, path: Path) -> str:
        return str(path.relative_to(layout.root))

    def _abs_path(self, layout: VaultLayout, rel_path: str) -> Path:
        return layout.root / rel_path

    def _resolve_raw_path(self, layout: VaultLayout, filename: str) -> Path:
        """Pick the on-disk path for a raw copy, disambiguating collisions.

        Normally ``docs/raw/<filename>``; if that file already exists (e.g. a
        different source file with the same basename was ingested earlier),
        append a numeric suffix before the extension to keep names unique
        rather than overwriting the other document's raw copy.
        """
        folder = layout.docs_raw_dir
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

    def find_by_identity(self, source_path: str, content_hash: str) -> Document | None:
        layout = self._layout()
        conn = sqlite3.connect(layout.db_path)
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

    def add(
        self, source_path: Path, content_hash: str, extracted_text: str, name: str
    ) -> Document:
        layout = self._layout()
        raw_path = self._resolve_raw_path(layout, source_path.name)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, raw_path)
        raw_rel_path = self._rel_path(layout, raw_path)

        ingested_at = datetime.now(timezone.utc).isoformat()
        status = "ingested"

        conn = sqlite3.connect(layout.db_path)
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

                processed_path = layout.docs_processed_dir / f"{doc_id}.md"
                processed_path.parent.mkdir(parents=True, exist_ok=True)
                processed_rel_path = self._rel_path(layout, processed_path)
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

    def list(self) -> list[Document]:
        layout = self._layout()
        conn = sqlite3.connect(layout.db_path)
        try:
            rows = conn.execute(
                "SELECT id, name, source_path, content_hash, raw_path, processed_path, "
                "ingested_at, status FROM documents ORDER BY id"
            ).fetchall()
        finally:
            conn.close()
        return [self._row_to_document(row) for row in rows]

    def get(self, id: int) -> Document | None:
        layout = self._layout()
        conn = sqlite3.connect(layout.db_path)
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

    def read_processed(self, id: int) -> str | None:
        layout = self._layout()
        conn = sqlite3.connect(layout.db_path)
        try:
            row = conn.execute(
                "SELECT processed_path FROM documents WHERE id = ?",
                (id,),
            ).fetchone()
        finally:
            conn.close()

        if row is None or row[0] is None:
            return None
        path = self._abs_path(layout, row[0])
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def remove(self, id: int) -> None:
        layout = self._layout()
        conn = sqlite3.connect(layout.db_path)
        try:
            row = conn.execute(
                "SELECT raw_path, processed_path FROM documents WHERE id = ?",
                (id,),
            ).fetchone()
            with conn:
                conn.execute("DELETE FROM documents WHERE id = ?", (id,))
                if row is not None:
                    raw_path, processed_path = row
                    if raw_path is not None:
                        abs_raw_path = self._abs_path(layout, raw_path)
                        if abs_raw_path.exists():
                            abs_raw_path.unlink()
                    if processed_path is not None:
                        abs_processed_path = self._abs_path(layout, processed_path)
                        if abs_processed_path.exists():
                            abs_processed_path.unlink()
        finally:
            conn.close()

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

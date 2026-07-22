"""DB layer: persistence for chunks, embeddings, and the FTS keyword index.

Chunks (and their embeddings) are *derived* index data, not source of truth
like ``docs/processed/`` or entity markdown files — they live only in
SQLite, produced by chunking + embedding the authoritative markdown bodies.
This module owns all reads/writes of the ``chunks`` / ``chunks_fts`` /
``index_state`` tables created by the ``forte init`` bootstrap (see
``db/schema.py``).

The key invariant is "replace, don't append": :meth:`IndexRepository.
reindex_source` swaps out *all* chunks/embeddings/FTS rows for a given
(source_type, source_id) inside a single transaction, so re-embedding a doc
or entity on edit never leaves orphaned chunks behind.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from forte.domain.vault import VaultLayout


@dataclass(frozen=True)
class ChunkInput:
    """One chunk of source text plus its embedding, ready to be indexed."""

    chunk_index: int
    text: str
    embedding: list[float]


@dataclass(frozen=True)
class EmbeddingRow:
    """A single stored chunk with its embedding, for a brute-force vector scan."""

    chunk_id: int
    source_type: str
    source_id: int
    text: str
    embedding: np.ndarray


@dataclass(frozen=True)
class KeywordHit:
    """A single chunk matched by an FTS5 keyword query."""

    chunk_id: int
    source_type: str
    source_id: int
    text: str
    rank: float


@dataclass(frozen=True)
class ChunkSource:
    """The (source_type, source_id) that a chunk belongs to."""

    source_type: str
    source_id: int


_INDEX_MODEL_KEY = "embedding_model"


class IndexRepository:
    """Read/write access to chunks, embeddings, and the FTS index for a vault."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._layout = VaultLayout(root)

    def reindex_source(
        self,
        source_type: str,
        source_id: int,
        chunks: list[ChunkInput],
        model: str,
    ) -> None:
        """Replace all chunks/embeddings/FTS rows for a source with ``chunks``.

        Runs in a single transaction: existing chunk ids for
        ``(source_type, source_id)`` are gathered, their ``chunks_fts`` rows
        deleted, then their ``chunks`` rows deleted, then the new chunks are
        inserted (capturing new autoincrement ids) followed by matching
        ``chunks_fts`` rows. This ordering keeps the FTS index in sync and
        leaves no orphaned rows when a source shrinks or its text changes.
        """
        conn = sqlite3.connect(self._layout.db_path)
        try:
            with conn:
                self._delete_source_rows(conn, source_type, source_id)
                for chunk in chunks:
                    cursor = conn.execute(
                        "INSERT INTO chunks "
                        "(source_type, source_id, chunk_index, text, embedding, model) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            source_type,
                            source_id,
                            chunk.chunk_index,
                            chunk.text,
                            _vector_to_blob(chunk.embedding),
                            model,
                        ),
                    )
                    chunk_id = cursor.lastrowid
                    conn.execute(
                        "INSERT INTO chunks_fts (text, chunk_id) VALUES (?, ?)",
                        (chunk.text, chunk_id),
                    )
        finally:
            conn.close()

    def delete_source(self, source_type: str, source_id: int) -> None:
        """Delete all chunks + their ``chunks_fts`` rows for a source."""
        conn = sqlite3.connect(self._layout.db_path)
        try:
            with conn:
                self._delete_source_rows(conn, source_type, source_id)
        finally:
            conn.close()

    @staticmethod
    def _delete_source_rows(
        conn: sqlite3.Connection, source_type: str, source_id: int
    ) -> None:
        """Delete existing chunks_fts + chunks rows for a source (FTS first)."""
        chunk_ids = [
            row[0]
            for row in conn.execute(
                "SELECT id FROM chunks WHERE source_type = ? AND source_id = ?",
                (source_type, source_id),
            ).fetchall()
        ]
        for chunk_id in chunk_ids:
            conn.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,))
        conn.execute(
            "DELETE FROM chunks WHERE source_type = ? AND source_id = ?",
            (source_type, source_id),
        )

    def all_embeddings(self) -> list[EmbeddingRow]:
        """Return every chunk with its embedding, for a brute-force vector scan."""
        conn = sqlite3.connect(self._layout.db_path)
        try:
            rows = conn.execute(
                "SELECT id, source_type, source_id, text, embedding FROM chunks"
            ).fetchall()
        finally:
            conn.close()
        return [
            EmbeddingRow(
                chunk_id=row[0],
                source_type=row[1],
                source_id=row[2],
                text=row[3],
                embedding=_blob_to_vector(row[4]),
            )
            for row in rows
        ]

    def keyword_search(self, query: str, limit: int | None = None) -> list[KeywordHit]:
        """Run an FTS5 MATCH query and return matching chunk rows, best rank first.

        The query is sanitized so FTS-special characters (punctuation,
        unmatched quotes, boolean operators like ``AND``/``NOT``) don't raise
        an FTS5 syntax error — each whitespace-separated term is treated as a
        literal, double-quoted phrase and the terms are ANDed together.
        """
        match_expr = _sanitize_fts_query(query)
        if not match_expr:
            return []

        sql = (
            "SELECT c.id, c.source_type, c.source_id, c.text, chunks_fts.rank "
            "FROM chunks_fts "
            "JOIN chunks c ON c.id = chunks_fts.chunk_id "
            "WHERE chunks_fts MATCH ? "
            "ORDER BY chunks_fts.rank"
        )
        params: tuple = (match_expr,)
        if limit is not None:
            sql += " LIMIT ?"
            params = (match_expr, limit)

        conn = sqlite3.connect(self._layout.db_path)
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
        return [
            KeywordHit(
                chunk_id=row[0],
                source_type=row[1],
                source_id=row[2],
                text=row[3],
                rank=row[4],
            )
            for row in rows
        ]

    def get_chunk_source(self, chunk_id: int) -> ChunkSource | None:
        """Return the (source_type, source_id) owning ``chunk_id``, or ``None``."""
        conn = sqlite3.connect(self._layout.db_path)
        try:
            row = conn.execute(
                "SELECT source_type, source_id FROM chunks WHERE id = ?",
                (chunk_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return ChunkSource(source_type=row[0], source_id=row[1])

    def get_index_model(self) -> str | None:
        """Return the vault-level indexed embedding model, or ``None`` if unset."""
        conn = sqlite3.connect(self._layout.db_path)
        try:
            row = conn.execute(
                "SELECT value FROM index_state WHERE key = ?",
                (_INDEX_MODEL_KEY,),
            ).fetchone()
        finally:
            conn.close()
        return row[0] if row is not None else None

    def set_index_model(self, model: str) -> None:
        """Set the vault-level indexed embedding model."""
        conn = sqlite3.connect(self._layout.db_path)
        try:
            with conn:
                conn.execute(
                    "INSERT INTO index_state (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (_INDEX_MODEL_KEY, model),
                )
        finally:
            conn.close()


def _vector_to_blob(vec: list[float]) -> bytes:
    """Serialize an embedding vector to float32 bytes for the ``embedding`` BLOB."""
    return np.asarray(vec, dtype=np.float32).tobytes()


def _blob_to_vector(blob: bytes) -> np.ndarray:
    """Deserialize an ``embedding`` BLOB back into a float32 numpy array."""
    return np.frombuffer(blob, dtype=np.float32)


def _sanitize_fts_query(query: str) -> str:
    """Turn free-form user text into a safe FTS5 MATCH expression.

    Each whitespace-separated term is wrapped in double quotes (with any
    embedded quote escaped) so punctuation and FTS operator keywords are
    treated as literal text rather than syntax, then the terms are joined
    with implicit AND.
    """
    terms = query.split()
    quoted = [f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms]
    return " ".join(quoted)

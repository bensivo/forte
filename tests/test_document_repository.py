"""Integration tests for the document DB repository (real SQLite + real files)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from forte.db.document_repository import DocumentRepository
from forte.domain.document import compute_content_hash
from forte.domain.document_markdown import from_markdown
from forte.domain.vault import VaultLayout
from forte.services.init import init


def _vault(tmp_path: Path) -> Path:
    init(tmp_path)
    return tmp_path


def _row(db_path: Path, doc_id: int) -> tuple | None:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT id, name, source_path, content_hash, raw_path, processed_path, "
            "ingested_at, status FROM documents WHERE id = ?",
            (doc_id,),
        ).fetchone()


def test_add_writes_raw_copy_processed_file_and_row(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = DocumentRepository(tmp_path)
    layout = VaultLayout(tmp_path)

    source = tmp_path / "source" / "note.txt"
    source.parent.mkdir(parents=True)
    source.write_text("hello world", encoding="utf-8")
    content_hash = compute_content_hash(source.read_bytes())

    stored = repo.add(source, content_hash, "hello world extracted text", "note")

    assert stored.id is not None
    assert stored.raw_path == "docs/raw/note.txt"
    assert stored.processed_path == f"docs/processed/{stored.id}.md"

    raw_path = layout.docs_raw_dir / "note.txt"
    assert raw_path.is_file()
    assert raw_path.read_text(encoding="utf-8") == "hello world"

    processed_path = layout.docs_processed_dir / f"{stored.id}.md"
    assert processed_path.is_file()
    parsed = from_markdown(processed_path.read_text(encoding="utf-8"))
    assert parsed.source_path == str(source)
    assert parsed.content_hash == content_hash
    assert parsed.body == "hello world extracted text"

    row = _row(layout.db_path, stored.id)
    assert row is not None
    assert row[1] == "note"
    assert row[2] == str(source)
    assert row[3] == content_hash
    assert row[4] == "docs/raw/note.txt"
    assert row[5] == f"docs/processed/{stored.id}.md"


def test_get_round_trips(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = DocumentRepository(tmp_path)

    source = tmp_path / "note.txt"
    source.write_text("hi", encoding="utf-8")
    content_hash = compute_content_hash(source.read_bytes())

    stored = repo.add(source, content_hash, "hi", "note")

    got = repo.get(stored.id)
    assert got is not None
    assert got.source_path == str(source)
    assert got.content_hash == content_hash
    assert got.raw_path == stored.raw_path
    assert got.processed_path == stored.processed_path


def test_get_missing_returns_none(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = DocumentRepository(tmp_path)

    assert repo.get(999) is None


def test_list_orders_by_id(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = DocumentRepository(tmp_path)

    s1 = tmp_path / "a.txt"
    s1.write_text("a", encoding="utf-8")
    s2 = tmp_path / "b.txt"
    s2.write_text("b", encoding="utf-8")

    d1 = repo.add(s1, compute_content_hash(s1.read_bytes()), "a", "doc-a")
    d2 = repo.add(s2, compute_content_hash(s2.read_bytes()), "b", "doc-b")

    ids = [d.id for d in repo.list()]
    assert ids == [d1.id, d2.id]


def test_find_by_identity(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = DocumentRepository(tmp_path)

    source = tmp_path / "note.txt"
    source.write_text("hi", encoding="utf-8")
    content_hash = compute_content_hash(source.read_bytes())

    stored = repo.add(source, content_hash, "hi", "note")

    found = repo.find_by_identity(str(source), content_hash)
    assert found is not None
    assert found.id == stored.id

    assert repo.find_by_identity(str(source), "different-hash") is None
    assert repo.find_by_identity("/nonexistent/path.txt", content_hash) is None


def test_remove_deletes_row_and_files(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = DocumentRepository(tmp_path)
    layout = VaultLayout(tmp_path)

    source = tmp_path / "note.txt"
    source.write_text("hi", encoding="utf-8")
    content_hash = compute_content_hash(source.read_bytes())
    stored = repo.add(source, content_hash, "hi", "note")

    raw_path = layout.docs_raw_dir / "note.txt"
    processed_path = layout.docs_processed_dir / f"{stored.id}.md"
    assert raw_path.is_file()
    assert processed_path.is_file()

    repo.remove(stored.id)

    assert repo.get(stored.id) is None
    assert _row(layout.db_path, stored.id) is None
    assert not raw_path.exists()
    assert not processed_path.exists()


def test_remove_missing_files_does_not_raise(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = DocumentRepository(tmp_path)
    layout = VaultLayout(tmp_path)

    source = tmp_path / "note.txt"
    source.write_text("hi", encoding="utf-8")
    content_hash = compute_content_hash(source.read_bytes())
    stored = repo.add(source, content_hash, "hi", "note")

    (layout.docs_raw_dir / "note.txt").unlink()
    (layout.docs_processed_dir / f"{stored.id}.md").unlink()

    repo.remove(stored.id)

    assert repo.get(stored.id) is None


def test_raw_copy_filename_collision_disambiguates(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = DocumentRepository(tmp_path)
    layout = VaultLayout(tmp_path)

    dir_a = tmp_path / "a"
    dir_a.mkdir()
    dir_b = tmp_path / "b"
    dir_b.mkdir()

    source_a = dir_a / "note.txt"
    source_a.write_text("content A", encoding="utf-8")
    source_b = dir_b / "note.txt"
    source_b.write_text("content B", encoding="utf-8")

    first = repo.add(source_a, compute_content_hash(source_a.read_bytes()), "text A", "note A")
    second = repo.add(source_b, compute_content_hash(source_b.read_bytes()), "text B", "note B")

    assert first.raw_path == "docs/raw/note.txt"
    assert second.raw_path == "docs/raw/note-1.txt"

    first_path = layout.docs_raw_dir / "note.txt"
    second_path = layout.docs_raw_dir / "note-1.txt"
    assert first_path.read_text(encoding="utf-8") == "content A"
    assert second_path.read_text(encoding="utf-8") == "content B"

"""Integration tests for the mention DB repository (real SQLite)."""

from __future__ import annotations

from pathlib import Path

from forte.db.mention_repository import MentionRepository
from forte.services.init import init


def _vault(tmp_path: Path) -> Path:
    init(tmp_path)
    return tmp_path


def test_add_creates_row_visible_via_list_for_doc(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = MentionRepository(tmp_path)

    repo.add(doc_id=1, entity_id=2, quote="hello world")

    mentions = repo.list_for_doc(1)
    assert len(mentions) == 1
    assert mentions[0].doc_id == 1
    assert mentions[0].entity_id == 2
    assert mentions[0].quote == "hello world"
    assert mentions[0].created_at


def test_exists_reports_true_and_false(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = MentionRepository(tmp_path)

    assert repo.exists(1, 2) is False
    repo.add(doc_id=1, entity_id=2)
    assert repo.exists(1, 2) is True


def test_remove_deletes_mention(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = MentionRepository(tmp_path)

    repo.add(doc_id=1, entity_id=2)
    repo.remove(1, 2)

    assert repo.list_for_doc(1) == []
    assert repo.exists(1, 2) is False


def test_remove_nonexistent_does_not_raise(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = MentionRepository(tmp_path)

    repo.remove(99, 99)  # should not raise


def test_list_for_doc_with_no_mentions_returns_empty_list(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = MentionRepository(tmp_path)

    assert repo.list_for_doc(1) == []


def test_add_one_mention_then_list_returns_exactly_that_one(tmp_path: Path) -> None:
    _vault(tmp_path)
    repo = MentionRepository(tmp_path)

    repo.add(doc_id=5, entity_id=10, quote="quote text")

    mentions = repo.list_for_doc(5)
    assert len(mentions) == 1
    assert mentions[0].entity_id == 10
    assert mentions[0].quote == "quote text"

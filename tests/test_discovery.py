"""Unit tests for git-style vault discovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from forte.services.discovery import VaultNotFoundError, find_vault_root


def test_find_vault_root_in_start_itself(tmp_path: Path) -> None:
    (tmp_path / ".forte").mkdir()

    assert find_vault_root(tmp_path) == tmp_path.resolve()


def test_find_vault_root_in_ancestor_several_levels_up(tmp_path: Path) -> None:
    (tmp_path / ".forte").mkdir()
    nested = tmp_path / "docs" / "raw" / "subdir"
    nested.mkdir(parents=True)

    assert find_vault_root(nested) == tmp_path.resolve()


def test_find_vault_root_raises_when_not_in_vault(tmp_path: Path) -> None:
    with pytest.raises(VaultNotFoundError):
        find_vault_root(tmp_path)

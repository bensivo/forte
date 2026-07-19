"""Unit tests for the VaultLayout domain module.

VaultLayout is pure path arithmetic, so these tests only exercise path
composition and the ordering/contents of `all_dirs()`. No filesystem I/O.
"""

from __future__ import annotations

from pathlib import Path

from forte.domain.vault import VaultLayout


def test_forte_dir_is_dot_forte_under_root() -> None:
    layout = VaultLayout(root=Path("/some/vault"))
    assert layout.forte_dir == Path("/some/vault/.forte")


def test_config_path_is_under_forte_dir() -> None:
    layout = VaultLayout(root=Path("/some/vault"))
    assert layout.config_path == Path("/some/vault/.forte/config.yaml")


def test_db_path_is_under_forte_dir() -> None:
    layout = VaultLayout(root=Path("/some/vault"))
    assert layout.db_path == Path("/some/vault/.forte/index.db")


def test_docs_raw_dir_composition() -> None:
    layout = VaultLayout(root=Path("/some/vault"))
    assert layout.docs_raw_dir == Path("/some/vault/docs/raw")


def test_docs_processed_dir_composition() -> None:
    layout = VaultLayout(root=Path("/some/vault"))
    assert layout.docs_processed_dir == Path("/some/vault/docs/processed")


def test_entities_dir_composition() -> None:
    layout = VaultLayout(root=Path("/some/vault"))
    assert layout.entities_dir == Path("/some/vault/entities")


def test_relative_root_stays_relative() -> None:
    layout = VaultLayout(root=Path("my-vault"))
    assert layout.forte_dir == Path("my-vault/.forte")
    assert layout.config_path == Path("my-vault/.forte/config.yaml")
    assert layout.docs_raw_dir == Path("my-vault/docs/raw")
    assert layout.entities_dir == Path("my-vault/entities")


def test_all_dirs_contents() -> None:
    root = Path("/some/vault")
    layout = VaultLayout(root=root)
    assert set(layout.all_dirs()) == {
        layout.forte_dir,
        layout.root / "docs",
        layout.docs_raw_dir,
        layout.docs_processed_dir,
        layout.entities_dir,
    }


def test_all_dirs_parents_precede_children() -> None:
    """Sequential mkdir must be safe — a parent must appear before its child."""
    layout = VaultLayout(root=Path("/some/vault"))
    dirs = layout.all_dirs()
    for i, d in enumerate(dirs):
        for earlier in dirs[:i]:
            # No later entry should be an ancestor of an earlier one.
            assert d not in earlier.parents, (
                f"{earlier} appears before its ancestor {d}"
            )


def test_all_dirs_excludes_per_schema_entity_subfolders() -> None:
    layout = VaultLayout(root=Path("/some/vault"))
    dirs = layout.all_dirs()
    # Only the top-level entities/ dir is included; no children of it.
    entity_children = [d for d in dirs if layout.entities_dir in d.parents]
    assert entity_children == []


def test_all_dirs_excludes_files() -> None:
    layout = VaultLayout(root=Path("/some/vault"))
    dirs = layout.all_dirs()
    assert layout.config_path not in dirs
    assert layout.db_path not in dirs


def test_no_io_for_nonexistent_root(tmp_path: Path) -> None:
    """Constructing and querying a layout must not touch the filesystem."""
    missing_root = tmp_path / "does-not-exist"
    assert not missing_root.exists()

    layout = VaultLayout(root=missing_root)
    _ = layout.forte_dir
    _ = layout.config_path
    _ = layout.db_path
    _ = layout.docs_raw_dir
    _ = layout.docs_processed_dir
    _ = layout.entities_dir
    _ = layout.all_dirs()

    # Nothing should have been created.
    assert not missing_root.exists()


def test_layout_is_frozen() -> None:
    """VaultLayout is a frozen dataclass — root cannot be mutated."""
    layout = VaultLayout(root=Path("/some/vault"))
    try:
        layout.root = Path("/other")  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("VaultLayout.root should be immutable")

"""Unit tests for the new `forte.model.vault` module.

`VaultLayout` is pure path arithmetic, so most of these tests only exercise
path composition and the ordering/contents of `all_dirs()`. No filesystem
I/O. The remaining tests cover the `Vault` model and the `VaultError`
exception hierarchy.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forte.model.vault import (
    InvalidVaultNameError,
    NoDefaultVaultError,
    Vault,
    VaultAlreadyRegisteredError,
    VaultError,
    VaultLayout,
    VaultNotFoundError,
    VaultTargetConflictError,
)


# --- VaultLayout -------------------------------------------------------------


def test_no_forte_dir_property() -> None:
    layout = VaultLayout(root=Path("/some/vault"))
    assert not hasattr(layout, "forte_dir")


def test_db_path_is_forte_db_under_root() -> None:
    layout = VaultLayout(root=Path("/some/vault"))
    assert layout.db_path == Path("/some/vault/forte.db")


def test_config_path_is_forte_yaml_under_root() -> None:
    layout = VaultLayout(root=Path("/some/vault"))
    assert layout.config_path == Path("/some/vault/forte.yaml")


def test_docs_raw_dir_composition() -> None:
    layout = VaultLayout(root=Path("/some/vault"))
    assert layout.docs_raw_dir == Path("/some/vault/docs/raw")


def test_docs_processed_dir_composition() -> None:
    layout = VaultLayout(root=Path("/some/vault"))
    assert layout.docs_processed_dir == Path("/some/vault/docs/processed")


def test_docs_staging_dir_composition() -> None:
    layout = VaultLayout(root=Path("/some/vault"))
    assert layout.docs_staging_dir == Path("/some/vault/docs/staging")


def test_entities_dir_composition() -> None:
    layout = VaultLayout(root=Path("/some/vault"))
    assert layout.entities_dir == Path("/some/vault/entities")


def test_relative_root_stays_relative() -> None:
    layout = VaultLayout(root=Path("my-vault"))
    assert layout.db_path == Path("my-vault/forte.db")
    assert layout.config_path == Path("my-vault/forte.yaml")
    assert layout.docs_raw_dir == Path("my-vault/docs/raw")
    assert layout.entities_dir == Path("my-vault/entities")


def test_all_dirs_contents_excludes_forte_dir() -> None:
    root = Path("/some/vault")
    layout = VaultLayout(root=root)
    assert set(layout.all_dirs()) == {
        layout.docs_dir,
        layout.docs_raw_dir,
        layout.docs_processed_dir,
        layout.docs_staging_dir,
        layout.entities_dir,
    }


def test_all_dirs_parents_precede_children() -> None:
    """Sequential mkdir must be safe — a parent must appear before its child."""
    layout = VaultLayout(root=Path("/some/vault"))
    dirs = layout.all_dirs()
    for i, d in enumerate(dirs):
        for earlier in dirs[:i]:
            assert d not in earlier.parents, (
                f"{earlier} appears before its ancestor {d}"
            )


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
    _ = layout.config_path
    _ = layout.db_path
    _ = layout.docs_raw_dir
    _ = layout.docs_processed_dir
    _ = layout.docs_staging_dir
    _ = layout.entities_dir
    _ = layout.all_dirs()

    assert not missing_root.exists()


def test_layout_is_frozen() -> None:
    layout = VaultLayout(root=Path("/some/vault"))
    with pytest.raises(Exception):
        layout.root = Path("/other")  # type: ignore[misc]


# --- Vault model ---------------------------------------------------------------


def test_vault_holds_name_and_path() -> None:
    vault = Vault(name="personal", path=Path("/Users/x/notes"))
    assert vault.name == "personal"
    assert vault.path == Path("/Users/x/notes")


def test_vault_is_frozen() -> None:
    vault = Vault(name="personal", path=Path("/Users/x/notes"))
    with pytest.raises(Exception):
        vault.name = "other"  # type: ignore[misc]


# --- VaultError hierarchy -------------------------------------------------------


@pytest.mark.parametrize(
    "exc_cls",
    [
        VaultAlreadyRegisteredError,
        VaultNotFoundError,
        NoDefaultVaultError,
        VaultTargetConflictError,
        InvalidVaultNameError,
    ],
)
def test_subclasses_derive_from_vault_error(exc_cls: type[Exception]) -> None:
    assert issubclass(exc_cls, VaultError)


def test_vault_error_derives_from_exception() -> None:
    assert issubclass(VaultError, Exception)

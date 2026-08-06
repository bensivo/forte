"""Unit tests for VaultService, driven exactly as a controller would drive it."""

from __future__ import annotations

from pathlib import Path

import pytest

from forte.interface.vault_fs import IVaultFs
from forte.interface.vault_registry import IVaultRegistry
from forte.model.vault import (
    InvalidVaultNameError,
    NoDefaultVaultError,
    Vault,
    VaultAlreadyRegisteredError,
    VaultLayout,
    VaultNotFoundError,
    VaultTargetConflictError,
)
from forte.service.vault_service import VaultService


class FakeVaultRegistry(IVaultRegistry):
    """In-memory IVaultRegistry that records every mutating call."""

    def __init__(self) -> None:
        self.vaults: dict[str, Vault] = {}
        self.default: str | None = None
        self.calls: list[tuple] = []

    def check_exists(self, name: str) -> bool:
        return name in self.vaults

    def add(self, vault: Vault) -> None:
        self.calls.append(("add", vault))
        self.vaults[vault.name] = vault

    def get(self, name: str) -> Vault | None:
        return self.vaults.get(name)

    def list(self) -> list[Vault]:
        return [self.vaults[n] for n in sorted(self.vaults)]

    def remove(self, name: str) -> None:
        self.calls.append(("remove", name))
        self.vaults.pop(name, None)

    def get_default(self) -> str | None:
        return self.default

    def set_default(self, name: str | None) -> None:
        self.calls.append(("set_default", name))
        self.default = name


class FakeVaultFs(IVaultFs):
    """In-memory IVaultFs that records writes and fakes an existing tree."""

    def __init__(self, existing: set[Path] | None = None) -> None:
        self.existing: set[Path] = set(existing or set())
        self.made_dirs: list[Path] = []
        self.configs: list[Path] = []
        self.dbs: list[Path] = []

    @property
    def writes(self) -> list[Path]:
        return self.made_dirs + self.configs + self.dbs

    def exists(self, path: Path) -> bool:
        return path in self.existing

    def make_dirs(self, path: Path) -> None:
        self.made_dirs.append(path)
        self.existing.add(path)

    def write_default_config(self, path: Path) -> None:
        self.configs.append(path)
        self.existing.add(path)

    def init_db(self, path: Path) -> None:
        self.dbs.append(path)
        self.existing.add(path)


@pytest.fixture
def registry() -> FakeVaultRegistry:
    return FakeVaultRegistry()


@pytest.fixture
def vault_fs() -> FakeVaultFs:
    return FakeVaultFs()


@pytest.fixture
def service(registry: FakeVaultRegistry, vault_fs: FakeVaultFs) -> VaultService:
    return VaultService(registry, vault_fs)


# --- create_vault: happy paths ----------------------------------------------


def test_create_vault_creates_dirs_config_db_and_registers(
    service: VaultService,
    registry: FakeVaultRegistry,
    vault_fs: FakeVaultFs,
    tmp_path: Path,
) -> None:
    vault = service.create_vault("personal", tmp_path)

    layout = VaultLayout(tmp_path.resolve())
    assert vault == Vault(name="personal", path=tmp_path.resolve())
    assert vault_fs.made_dirs == layout.all_dirs()
    assert vault_fs.configs == [layout.config_path]
    assert vault_fs.dbs == [layout.db_path]
    assert registry.get("personal") == vault


def test_create_vault_resolves_relative_path(
    service: VaultService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    vault = service.create_vault("personal", Path("."))

    assert vault.path == tmp_path.resolve()
    assert vault.path.is_absolute()


def test_create_vault_in_existing_empty_directory_works(
    service: VaultService, vault_fs: FakeVaultFs, tmp_path: Path
) -> None:
    # The vault root already exists; only its children get created.
    vault_fs.existing.add(tmp_path.resolve())

    service.create_vault("personal", tmp_path)

    assert tmp_path.resolve() not in vault_fs.made_dirs
    assert vault_fs.made_dirs == VaultLayout(tmp_path.resolve()).all_dirs()


def test_create_vault_sets_default_when_none_set(
    service: VaultService, registry: FakeVaultRegistry, tmp_path: Path
) -> None:
    service.create_vault("personal", tmp_path)

    assert registry.get_default() == "personal"


def test_create_vault_keeps_existing_default(
    service: VaultService, registry: FakeVaultRegistry, tmp_path: Path
) -> None:
    service.create_vault("personal", tmp_path / "a")
    service.create_vault("work", tmp_path / "b")

    assert registry.get_default() == "personal"


# --- create_vault: validation branches --------------------------------------


@pytest.mark.parametrize(
    "bad_name", ["Personal", "with space", "with/slash", "", "-", "café"]
)
def test_create_vault_invalid_name(
    service: VaultService, vault_fs: FakeVaultFs, tmp_path: Path, bad_name: str
) -> None:
    with pytest.raises(InvalidVaultNameError):
        service.create_vault(bad_name, tmp_path)

    assert vault_fs.writes == []


def test_create_vault_duplicate_name(
    service: VaultService,
    registry: FakeVaultRegistry,
    vault_fs: FakeVaultFs,
    tmp_path: Path,
) -> None:
    registry.add(Vault(name="personal", path=tmp_path / "elsewhere"))

    with pytest.raises(VaultAlreadyRegisteredError):
        service.create_vault("personal", tmp_path)

    assert vault_fs.writes == []


@pytest.mark.parametrize("conflict", ["forte.db", "forte.yaml", "docs", "entities"])
def test_create_vault_target_conflict(
    service: VaultService,
    registry: FakeVaultRegistry,
    vault_fs: FakeVaultFs,
    tmp_path: Path,
    conflict: str,
) -> None:
    vault_fs.existing.add(tmp_path.resolve() / conflict)

    with pytest.raises(VaultTargetConflictError):
        service.create_vault("personal", tmp_path)

    assert vault_fs.writes == []
    assert registry.list() == []
    assert registry.get_default() is None


def test_create_vault_failed_validation_makes_no_registry_calls(
    service: VaultService, registry: FakeVaultRegistry, tmp_path: Path
) -> None:
    vault_fs_existing = VaultLayout(tmp_path.resolve()).db_path
    service.vault_fs.existing.add(vault_fs_existing)

    with pytest.raises(VaultTargetConflictError):
        service.create_vault("personal", tmp_path)

    assert registry.calls == []


# --- list / get -------------------------------------------------------------


def test_list_vaults_empty(service: VaultService) -> None:
    assert service.list_vaults() == []


def test_list_vaults_returns_registered(
    service: VaultService, registry: FakeVaultRegistry, tmp_path: Path
) -> None:
    registry.add(Vault(name="work", path=tmp_path / "w"))
    registry.add(Vault(name="personal", path=tmp_path / "p"))

    assert [v.name for v in service.list_vaults()] == ["personal", "work"]


def test_get_vault_returns_vault(
    service: VaultService, registry: FakeVaultRegistry, tmp_path: Path
) -> None:
    registry.add(Vault(name="personal", path=tmp_path))

    assert service.get_vault("personal") == Vault(name="personal", path=tmp_path)


def test_get_vault_unknown_name(service: VaultService) -> None:
    with pytest.raises(VaultNotFoundError):
        service.get_vault("nope")


# --- remove_vault -----------------------------------------------------------


def test_remove_vault_unregisters_only(
    service: VaultService,
    registry: FakeVaultRegistry,
    vault_fs: FakeVaultFs,
    tmp_path: Path,
) -> None:
    service.create_vault("personal", tmp_path)
    writes_before = list(vault_fs.writes)

    service.remove_vault("personal")

    assert registry.list() == []
    assert vault_fs.writes == writes_before


def test_remove_vault_clears_default(
    service: VaultService, registry: FakeVaultRegistry, tmp_path: Path
) -> None:
    service.create_vault("personal", tmp_path / "a")
    service.create_vault("work", tmp_path / "b")
    assert registry.get_default() == "personal"

    service.remove_vault("personal")

    assert registry.get_default() is None


def test_remove_vault_non_default_keeps_default(
    service: VaultService, registry: FakeVaultRegistry, tmp_path: Path
) -> None:
    service.create_vault("personal", tmp_path / "a")
    service.create_vault("work", tmp_path / "b")

    service.remove_vault("work")

    assert registry.get_default() == "personal"


def test_remove_vault_unknown_name(
    service: VaultService, registry: FakeVaultRegistry
) -> None:
    with pytest.raises(VaultNotFoundError):
        service.remove_vault("nope")

    assert registry.calls == []


# --- set_default_vault ------------------------------------------------------


def test_set_default_vault(
    service: VaultService, registry: FakeVaultRegistry, tmp_path: Path
) -> None:
    registry.add(Vault(name="personal", path=tmp_path / "a"))
    registry.add(Vault(name="work", path=tmp_path / "b"))

    service.set_default_vault("work")

    assert registry.get_default() == "work"


def test_set_default_vault_unknown_name(
    service: VaultService, registry: FakeVaultRegistry
) -> None:
    with pytest.raises(VaultNotFoundError):
        service.set_default_vault("nope")

    assert registry.get_default() is None
    assert registry.calls == []


# --- resolve_vault ----------------------------------------------------------


def test_resolve_vault_by_name(
    service: VaultService, registry: FakeVaultRegistry, tmp_path: Path
) -> None:
    registry.add(Vault(name="work", path=tmp_path))

    assert service.resolve_vault("work") == Vault(name="work", path=tmp_path)


def test_resolve_vault_unknown_name(service: VaultService) -> None:
    with pytest.raises(VaultNotFoundError):
        service.resolve_vault("nope")


def test_resolve_vault_none_returns_default(
    service: VaultService, registry: FakeVaultRegistry, tmp_path: Path
) -> None:
    registry.add(Vault(name="personal", path=tmp_path / "a"))
    registry.add(Vault(name="work", path=tmp_path / "b"))
    registry.set_default("work")

    assert service.resolve_vault(None).name == "work"


def test_resolve_vault_none_without_default(service: VaultService) -> None:
    with pytest.raises(NoDefaultVaultError) as excinfo:
        service.resolve_vault(None)

    message = str(excinfo.value)
    assert "forte vault create" in message
    assert "forte vault set-default" in message


def test_resolve_vault_ignores_cwd(
    service: VaultService,
    registry: FakeVaultRegistry,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A vault-looking directory under cwd must not be discovered by walking up.
    (tmp_path / "forte.db").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(NoDefaultVaultError):
        service.resolve_vault(None)

    assert registry.list() == []


def test_resolve_vault_dangling_default(
    service: VaultService, registry: FakeVaultRegistry
) -> None:
    registry.set_default("ghost")

    with pytest.raises(VaultNotFoundError):
        service.resolve_vault(None)

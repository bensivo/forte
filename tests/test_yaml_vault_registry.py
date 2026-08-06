"""Unit tests for the YamlVaultRegistry client.

These always inject a tmp_path as the home dir so the real ~/.forte/ is
never touched.
"""

from __future__ import annotations

from pathlib import Path

from forte.client.yaml_vault_registry import YamlVaultRegistry
from forte.model.vault import Vault


def _registry(tmp_path: Path) -> YamlVaultRegistry:
    return YamlVaultRegistry(home_dir=tmp_path)


def test_missing_file_yields_no_vaults_and_no_default(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    assert registry.list() == []
    assert registry.get_default() is None
    assert registry.get("personal") is None
    assert registry.check_exists("personal") is False


def test_empty_file_yields_no_vaults_and_no_default(tmp_path: Path) -> None:
    config_dir = tmp_path / ".forte"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("", encoding="utf-8")

    registry = _registry(tmp_path)
    assert registry.list() == []
    assert registry.get_default() is None


def test_add_and_get_round_trip(tmp_path: Path) -> None:
    vault_dir = tmp_path / "notes"
    vault_dir.mkdir()
    registry = _registry(tmp_path)

    registry.add(Vault(name="personal", path=vault_dir))

    fetched = registry.get("personal")
    assert fetched is not None
    assert fetched.name == "personal"
    assert fetched.path == vault_dir.resolve()


def test_add_resolves_relative_paths_to_absolute(tmp_path: Path, monkeypatch) -> None:
    vault_dir = tmp_path / "notes"
    vault_dir.mkdir()
    monkeypatch.chdir(vault_dir)
    registry = _registry(tmp_path)

    registry.add(Vault(name="personal", path=Path(".")))

    fetched = registry.get("personal")
    assert fetched is not None
    assert fetched.path == vault_dir.resolve()
    assert fetched.path.is_absolute()


def test_check_exists_true_and_false(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    registry.add(Vault(name="personal", path=tmp_path / "notes"))

    assert registry.check_exists("personal") is True
    assert registry.check_exists("work") is False


def test_list_ordering(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    registry.add(Vault(name="zeta", path=tmp_path / "zeta"))
    registry.add(Vault(name="alpha", path=tmp_path / "alpha"))
    registry.add(Vault(name="mid", path=tmp_path / "mid"))

    names = [v.name for v in registry.list()]
    assert names == ["alpha", "mid", "zeta"]


def test_remove_unregisters_vault(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    registry.add(Vault(name="personal", path=tmp_path / "notes"))

    registry.remove("personal")

    assert registry.get("personal") is None
    assert registry.check_exists("personal") is False
    assert registry.list() == []


def test_remove_missing_vault_is_a_no_op(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    registry.remove("nonexistent")  # should not raise
    assert registry.list() == []


def test_default_get_and_set(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    registry.add(Vault(name="personal", path=tmp_path / "notes"))

    assert registry.get_default() is None

    registry.set_default("personal")

    assert registry.get_default() == "personal"


def test_removing_default_vault_leaves_default_name_dangling(tmp_path: Path) -> None:
    """The registry has no opinion on this — it just does what it's told.
    Deciding whether/how to clear the default is a VaultService concern."""
    registry = _registry(tmp_path)
    registry.add(Vault(name="personal", path=tmp_path / "notes"))
    registry.set_default("personal")

    registry.remove("personal")

    assert registry.get_default() == "personal"
    assert registry.get("personal") is None


def test_data_persists_across_registry_instances(tmp_path: Path) -> None:
    registry1 = _registry(tmp_path)
    registry1.add(Vault(name="personal", path=tmp_path / "notes"))
    registry1.set_default("personal")

    registry2 = _registry(tmp_path)
    assert registry2.get_default() == "personal"
    fetched = registry2.get("personal")
    assert fetched is not None
    assert fetched.name == "personal"


def test_creates_forte_dir_on_first_write(tmp_path: Path) -> None:
    config_dir = tmp_path / ".forte"
    assert not config_dir.exists()

    registry = _registry(tmp_path)
    registry.add(Vault(name="personal", path=tmp_path / "notes"))

    assert config_dir.exists()
    assert (config_dir / "config.yaml").exists()


def test_default_home_dir_uses_path_home(monkeypatch, tmp_path: Path) -> None:
    """Constructor arg defaults to Path.home() when not injected."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    registry = YamlVaultRegistry()
    assert registry._home_dir == tmp_path

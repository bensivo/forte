"""Tests for ConfigService (get_config / require_api_key).

Uses a FakeConfigStore for unit coverage of the resolution logic, plus one
regression test that reads back a `forte.yaml` written by the real
`LocalVaultFs.write_default_config` at `VaultLayout.config_path` — the
current vault-creation path — through the real `YamlConfigStore`.
"""

from __future__ import annotations

import pytest

from forte.client.fs_vault_fs import LocalVaultFs
from forte.client.yaml_config_store import YamlConfigStore
from forte.interface.config_store import IConfigStore
from forte.model.config import MissingAPIKeyError
from forte.model.vault import VaultContext, VaultLayout
from forte.service.config_service import ConfigService


class FakeConfigStore(IConfigStore):
    """In-memory IConfigStore test double, backed by a plain dict."""

    def __init__(self, data: dict | None = None):
        self._data = data or {}

    def read(self) -> dict:
        return self._data


def _service(data: dict | None = None) -> ConfigService:
    return ConfigService(FakeConfigStore(data))


def test_missing_file_uses_defaults():
    # Empty dict simulates a missing config file, same as FakeConfigStore().
    service = _service({})
    config = service.get_config()
    assert config.extraction_model == "claude-haiku-4-5"
    assert config.anthropic_api_key is None
    assert config.editor is None


def test_empty_file_uses_defaults():
    service = _service({})
    config = service.get_config()
    assert config.extraction_model == "claude-haiku-4-5"
    assert config.anthropic_api_key is None
    assert config.editor is None


def test_partial_keys_fill_in_remaining_defaults():
    service = _service({"model": {"extraction": "claude-sonnet-4-5"}})
    config = service.get_config()
    assert config.extraction_model == "claude-sonnet-4-5"
    assert config.anthropic_api_key is None
    assert config.editor is None


def test_env_var_interpolation_when_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
    service = _service({"api_keys": {"anthropic": "${ANTHROPIC_API_KEY}"}})
    config = service.get_config()
    assert config.anthropic_api_key == "sk-from-env"


def test_env_var_interpolation_when_unset_is_none(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    service = _service({"api_keys": {"anthropic": "${ANTHROPIC_API_KEY}"}})
    config = service.get_config()
    assert config.anthropic_api_key is None


def test_literal_api_key_used_as_is():
    service = _service({"api_keys": {"anthropic": "sk-literal"}})
    config = service.get_config()
    assert config.anthropic_api_key == "sk-literal"


def test_editor_value_resolves():
    service = _service({"editor": "vim"})
    config = service.get_config()
    assert config.editor == "vim"


def test_editor_with_command_and_args_resolves():
    service = _service({"editor": "code --wait"})
    config = service.get_config()
    assert config.editor == "code --wait"


def test_require_api_key_raises_when_none():
    service = _service({})
    with pytest.raises(MissingAPIKeyError):
        service.require_api_key()


def test_require_api_key_returns_key_when_present():
    service = _service({"api_keys": {"anthropic": "sk-123"}})
    assert service.require_api_key() == "sk-123"


# --- Regression test -------------------------------------------------------


def test_regression_reads_config_written_by_real_vault_create(tmp_path, monkeypatch):
    """A `forte.yaml` written by the real vault-create path (LocalVaultFs at
    VaultLayout.config_path) must be read back correctly by ConfigService.

    This is the scenario that the legacy `services/config.py` got wrong: it
    resolved the config path via the legacy `.forte/config.yaml` layout, so
    it silently fell back to defaults for any vault created by the new
    `forte vault create`, which writes `forte.yaml` at the vault root.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-regression")

    root = tmp_path / "myvault"
    layout = VaultLayout(root)
    for directory in layout.all_dirs():
        directory.mkdir(parents=True)

    fs = LocalVaultFs()
    fs.write_default_config(layout.config_path)

    # forte.yaml lands at the vault root, not under a `.forte/` subdirectory.
    assert layout.config_path == root / "forte.yaml"
    assert layout.config_path.exists()

    context = VaultContext()
    context.set_root(root)
    service = ConfigService(YamlConfigStore(context))

    config = service.get_config()
    assert config.extraction_model == "claude-haiku-4-5"
    assert config.anthropic_api_key == "sk-regression"
    assert config.editor is None

from pathlib import Path

import yaml

from forte.interface.vault_registry import IVaultRegistry
from forte.model.vault import Vault

# Name of the user-level registry file, written under the injected home dir.
_CONFIG_DIR_NAME = ".forte"
_CONFIG_FILE_NAME = "config.yaml"


class YamlVaultRegistry(IVaultRegistry):
    """
    YAML implementation of IVaultRegistry, backed by a single user-level
    file at ``<home>/.forte/config.yaml``. This is distinct from the
    per-vault ``forte.yaml`` config handled elsewhere — this file only
    tracks which vaults exist, where they live, and which is the default.

    The file holds a ``default: <name>`` key and a ``vaults:`` mapping of
    name -> absolute path, e.g.:

        default: personal
        vaults:
          personal: /Users/x/notes

    Reading a missing or empty file yields no vaults and no default rather
    than raising. The whole file is rewritten on every mutation.
    """

    def __init__(self, home_dir: Path | None = None):
        self._home_dir = home_dir if home_dir is not None else Path.home()

    def _config_dir(self) -> Path:
        return self._home_dir / _CONFIG_DIR_NAME

    def _config_path(self) -> Path:
        return self._config_dir() / _CONFIG_FILE_NAME

    def _read(self) -> dict:
        path = self._config_path()
        if not path.exists():
            return {"default": None, "vaults": {}}

        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            return {"default": None, "vaults": {}}

        vaults = loaded.get("vaults")
        if not isinstance(vaults, dict):
            vaults = {}

        default = loaded.get("default")
        if not isinstance(default, str):
            default = None

        return {"default": default, "vaults": vaults}

    def _write(self, data: dict) -> None:
        self._config_dir().mkdir(parents=True, exist_ok=True)
        content = {
            "default": data.get("default"),
            "vaults": data.get("vaults", {}),
        }
        self._config_path().write_text(
            yaml.safe_dump(content, sort_keys=True), encoding="utf-8"
        )

    def check_exists(self, name: str) -> bool:
        data = self._read()
        return name in data["vaults"]

    def add(self, vault: Vault) -> None:
        data = self._read()
        data["vaults"][vault.name] = str(Path(vault.path).resolve())
        self._write(data)

    def get(self, name: str) -> Vault | None:
        data = self._read()
        raw_path = data["vaults"].get(name)
        if raw_path is None:
            return None
        return Vault(name=name, path=Path(raw_path))

    def list(self) -> list[Vault]:
        data = self._read()
        return [
            Vault(name=name, path=Path(raw_path))
            for name, raw_path in sorted(data["vaults"].items())
        ]

    def remove(self, name: str) -> None:
        data = self._read()
        data["vaults"].pop(name, None)
        self._write(data)

    def get_default(self) -> str | None:
        data = self._read()
        return data["default"]

    def set_default(self, name: str | None) -> None:
        data = self._read()
        data["default"] = name
        self._write(data)

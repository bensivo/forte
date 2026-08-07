from __future__ import annotations

import yaml

from forte.interface.config_store import IConfigStore
from forte.model.vault import VaultContext, VaultLayout


class YamlConfigStore(IConfigStore):
    """
    YAML file implementation of IConfigStore. Reads ``<vault_root>/forte.yaml``
    via VaultLayout.

    Resolves the vault root from the injected `VaultContext` on every call,
    so it can be constructed unconditionally at wiring time, before the
    active vault is known — a missing vault only surfaces as a
    `NoDefaultVaultError` when `read()` is actually invoked.
    """

    def __init__(self, context: VaultContext):
        """
        Args:
            context (VaultContext): Holds the active vault root, resolved
                lazily on each call.
        """
        self._context = context

    def read(self) -> dict:
        root = self._context.get_root()
        config_path = VaultLayout(root).config_path

        if not config_path.exists():
            return {}

        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}

"""Service layer: git-style vault discovery.

Every command that operates on an *existing* vault (schema, entity, doc) walks
upward from the current directory looking for a `.forte/` directory. This does
filesystem I/O, so it lives in the service layer rather than the pure-path
`domain.vault` module.
"""

from __future__ import annotations

from pathlib import Path

from forte.domain.vault import VaultLayout


class VaultNotFoundError(Exception):
    """Raised when no `.forte/` directory is found walking up from the start dir."""


def find_vault_root(start: Path) -> Path:
    """Walk upward from `start` to find the vault root.

    Returns the first ancestor directory (inclusive of `start`) that contains a
    `.forte/` directory — the vault root, i.e. the directory that *contains*
    `.forte/`, not `.forte/` itself. Callers build a `VaultLayout` from it.

    Raises VaultNotFoundError if the filesystem root is reached without finding
    a vault.
    """
    current = start.resolve()

    while True:
        if VaultLayout(current).forte_dir.is_dir():
            return current

        parent = current.parent
        if parent == current:
            raise VaultNotFoundError(
                "Not inside a Forte vault (no .forte/ directory found)."
            )
        current = parent

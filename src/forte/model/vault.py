"""Vault filesystem layout and the Vault registry model.

A Forte vault can live anywhere on disk. It is identified by two files at
its root: ``forte.db`` (the SQLite index) and ``forte.yaml`` (per-vault
config). There is no internal ``.forte/`` directory — that legacy layout is
retired with this module. This is a clean break: existing ``.forte/``
vaults created by older builds are not migrated and will not be recognized
by this layout.
"""

import re
from dataclasses import dataclass
from pathlib import Path

# Vault names are user-facing registry keys; same slug rule as schema names.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True)
class VaultLayout:
    """Well-known paths inside a Forte vault rooted at ``root``.

    Pure path arithmetic only — no I/O happens here. Callers are
    responsible for creating or reading the paths this class computes.
    """

    root: Path

    @property
    def config_path(self) -> Path:
        """Path to the vault's configuration file."""
        return self.root / "forte.yaml"

    @property
    def db_path(self) -> Path:
        """Path to the vault's SQLite index database."""
        return self.root / "forte.db"

    @property
    def docs_dir(self) -> Path:
        """Path to the vault's top-level docs directory."""
        return self.root / "docs"

    @property
    def docs_raw_dir(self) -> Path:
        """Path to the directory holding raw, unprocessed documents."""
        return self.docs_dir / "raw"

    @property
    def docs_processed_dir(self) -> Path:
        """Path to the directory holding fully processed documents."""
        return self.docs_dir / "processed"

    @property
    def docs_staging_dir(self) -> Path:
        """Path to the directory holding documents pending processing."""
        return self.docs_dir / "staging"

    @property
    def entities_dir(self) -> Path:
        """Path to the vault's top-level entities directory."""
        return self.root / "entities"

    def all_dirs(self) -> list[Path]:
        """Directories that vault creation must create, in creation order.

        Per-schema subfolders under ``entities/`` are created lazily when
        schemas are added and are intentionally not included here.

        Returns:
            list[Path]: The directories to create, in the order they must
            be created.
        """
        return [
            self.docs_dir,
            self.docs_raw_dir,
            self.docs_processed_dir,
            self.docs_staging_dir,
            self.entities_dir,
        ]


@dataclass(frozen=True)
class Vault:
    """A registered vault: a user-facing name paired with its root path."""

    name: str
    path: Path


class VaultError(Exception):
    """Base class for vault errors."""


class VaultAlreadyRegisteredError(VaultError):
    """Raised when registering a vault name that is already taken."""


class VaultNotFoundError(VaultError):
    """Raised when a vault cannot be located: no vault is registered under
    the given name, or (during a directory walk) no vault was found in any
    ancestor directory."""


class NoDefaultVaultError(VaultError):
    """Raised when resolving the default vault but none has been set."""


class VaultTargetConflictError(VaultError):
    """Raised when creating a vault at a target directory that already
    contains a vault (``forte.db`` / ``forte.yaml``) or conflicting
    ``docs/`` / ``entities/`` folders."""


class InvalidVaultNameError(VaultError):
    """Raised when a vault name fails the slug validation rule
    (``^[a-z0-9][a-z0-9_-]*$``)."""


class VaultContext:
    """Holds the vault root selected for the current process invocation.

    The SQLite clients are constructed unconditionally at wiring time in
    ``main.py``, before any vault has been chosen (e.g. via a future
    ``--vault`` CLI option). A single ``VaultContext`` instance is shared
    across all of them so that a CLI-time decision — made once per
    invocation — can reach every client without threading a vault root
    parameter through every service and interface method. Clients read
    ``root`` lazily, on each method call, never in ``__init__``.
    """

    def __init__(self) -> None:
        self.root: Path | None = None

    def set_root(self, root: Path) -> None:
        """Sets the active vault root.

        Args:
            root (Path): The resolved vault root to make active.
        """
        self.root = root

    def get_root(self) -> Path:
        """Gets the active vault root.

        Returns:
            (Path) The currently active vault root.

        Raises:
            NoDefaultVaultError: If no vault root has been selected yet.
        """
        if self.root is None:
            raise NoDefaultVaultError(
                "No vault selected. Run 'forte vault create' or "
                "'forte vault set-default' to select one."
            )
        return self.root

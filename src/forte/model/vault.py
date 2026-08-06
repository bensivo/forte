"""Vault filesystem layout.

Pure path arithmetic for the well-known locations inside a Forte vault.
No I/O happens here — callers are responsible for creating or reading paths.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VaultLayout:
    """Well-known paths inside a Forte vault rooted at ``root``."""

    root: Path

    @property
    def forte_dir(self) -> Path:
        """Path to the vault's internal ``.forte`` directory."""
        return self.root / ".forte"

    @property
    def config_path(self) -> Path:
        """Path to the vault's configuration file."""
        return self.forte_dir / "config.yaml"

    @property
    def db_path(self) -> Path:
        """Path to the vault's SQLite index database."""
        return self.forte_dir / "index.db"

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
        """Directories that ``forte init`` must create, in creation order.

        Per-schema subfolders under ``entities/`` are created lazily when
        schemas are added and are intentionally not included here.

        Returns:
            list[Path]: The directories to create, in the order they must
            be created.
        """
        return [
            self.forte_dir,
            self.docs_dir,
            self.docs_raw_dir,
            self.docs_processed_dir,
            self.docs_staging_dir,
            self.entities_dir,
        ]


class VaultAlreadyExistsError(Exception):
    """Raised when initializing a vault in a directory that already contains one."""

"""Vault filesystem layout.

Pure path arithmetic for the well-known locations inside a Forte vault.
No I/O happens here — callers are responsible for creating or reading paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VaultLayout:
    """Well-known paths inside a Forte vault rooted at ``root``."""

    root: Path

    @property
    def forte_dir(self) -> Path:
        return self.root / ".forte"

    @property
    def config_path(self) -> Path:
        return self.forte_dir / "config.yaml"

    @property
    def db_path(self) -> Path:
        return self.forte_dir / "index.db"

    @property
    def docs_dir(self) -> Path:
        return self.root / "docs"

    @property
    def docs_raw_dir(self) -> Path:
        return self.docs_dir / "raw"

    @property
    def docs_processed_dir(self) -> Path:
        return self.docs_dir / "processed"

    @property
    def entities_dir(self) -> Path:
        return self.root / "entities"

    def all_dirs(self) -> list[Path]:
        """Directories that ``forte init`` must create, in creation order.

        Per-schema subfolders under ``entities/`` are created lazily when
        schemas are added and are intentionally not included here.
        """
        return [
            self.forte_dir,
            self.docs_dir,
            self.docs_raw_dir,
            self.docs_processed_dir,
            self.entities_dir,
        ]

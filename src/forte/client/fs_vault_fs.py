"""Local filesystem and SQLite implementation of the vault filesystem interface."""

from __future__ import annotations

from pathlib import Path

from forte.db.schema import initialize_database
from forte.interface.vault_fs import IVaultFs
from forte.services.config import write_default_config as _write_default_config


class LocalVaultFs(IVaultFs):
    """Concrete IVaultFs implementation backed by the local filesystem and SQLite.

    Uses the standard library `pathlib` for filesystem checks and directory
    creation, and delegates config file and database creation to the
    existing `forte.services.config` and `forte.db.schema` helpers.
    """

    def exists(self, path: Path) -> bool:
        """Check whether a path exists on the local filesystem.

        Args:
            path (Path): The path to check.

        Returns:
            (bool) True if the path exists, False otherwise.
        """
        return path.exists()

    def make_dirs(self, path: Path) -> None:
        """Create a directory, including any missing parent directories.

        Fails loudly if any part of the path already exists.

        Args:
            path (Path): The directory path to create.

        Returns:
            None

        Raises:
            FileExistsError: if `path` (or a parent) already exists.
        """
        path.mkdir(parents=True)

    def write_default_config(self, path: Path) -> None:
        """Write the default Forte config file to `path`.

        Args:
            path (Path): The destination path for the config file.

        Returns:
            None

        Raises:
            FileExistsError: if `path` already exists.
        """
        _write_default_config(path)

    def init_db(self, path: Path) -> None:
        """Create a fresh SQLite database with the MVP schema at `path`.

        Args:
            path (Path): The destination path for the SQLite database file.

        Returns:
            None

        Raises:
            FileExistsError: if `path` already exists.
        """
        initialize_database(path)

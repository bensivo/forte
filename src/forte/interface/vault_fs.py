from abc import ABC, abstractmethod
from pathlib import Path


class IVaultFs(ABC):
    """
    Interface for the filesystem and database side effects needed to
    initialize a Forte vault. Implementations handle actually creating
    directories, writing config, and bootstrapping the index database.
    """

    @abstractmethod
    def exists(self, path: Path) -> bool:
        """
        Return whether the given path already exists.

        Args:
            path (Path): The filesystem path to check.

        Returns:
            (bool) True if the path exists, False otherwise.
        """
        pass

    @abstractmethod
    def make_dirs(self, path: Path) -> None:
        """
        Create the given directory, including any missing parents.

        Args:
            path (Path): The directory path to create.

        Returns:
            None
        """
        pass

    @abstractmethod
    def write_default_config(self, path: Path) -> None:
        """
        Write a default config.yaml at the given path.

        Args:
            path (Path): The path where the default config file should be written.

        Returns:
            None
        """
        pass

    @abstractmethod
    def init_db(self, path: Path) -> None:
        """
        Create and initialize a fresh SQLite index database at the given path.

        Args:
            path (Path): The path where the SQLite database file should be created.

        Returns:
            None
        """
        pass

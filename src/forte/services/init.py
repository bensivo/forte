"""Service layer: initialize a new Forte vault."""

from pathlib import Path

from forte.db.schema import initialize_database
from forte.domain.vault import VaultLayout
from forte.services.config import write_default_config


class VaultAlreadyExistsError(Exception):
    """Raised when `init` is called in a directory that already contains a vault."""


def init(root: Path) -> Path:
    """Initialize a new Forte vault rooted at `root`.

    Returns the absolute path of the vault root on success.
    Raises VaultAlreadyExistsError if `root/.forte/` already exists.
    """
    layout = VaultLayout(root)

    if layout.forte_dir.exists():
        raise VaultAlreadyExistsError(f"Forte vault already exists at {layout.forte_dir}")

    for conflict in (layout.docs_dir, layout.entities_dir):
        if conflict.exists():
            rel = conflict.relative_to(root) if conflict.is_relative_to(root) else conflict
            raise VaultAlreadyExistsError(
                f"{rel}/ folder already present. Please run forte init in an empty directory"
            )

    for directory in layout.all_dirs():
        directory.mkdir(parents=True)

    write_default_config(layout.config_path)
    initialize_database(layout.db_path)

    return root.resolve()

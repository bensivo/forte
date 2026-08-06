"""Service layer: initialize a new Forte vault."""

from pathlib import Path

from forte.interface.vault_fs import IVaultFs
from forte.model.vault import VaultAlreadyExistsError, VaultLayout


class InitService:
    """Implements vault initialization business logic.

    Coordinates creation of the vault directory structure, default
    configuration, and database, delegating all filesystem/db side
    effects to an injected IVaultFs implementation.
    """

    def __init__(self, vault_fs: IVaultFs):
        """Initializes the InitService.

        Args:
            vault_fs (IVaultFs): Implementation used to perform filesystem
                and database operations required to initialize a vault.
        """
        self.vault_fs = vault_fs

    def init_vault(self, root: Path) -> Path:
        """Initializes a new Forte vault rooted at `root`.

        Args:
            root (Path): The directory in which to initialize the vault.

        Returns:
            (Path) The absolute, resolved path of the vault root on success.

        Raises:
            VaultAlreadyExistsError: If `root/.forte/` already exists, or if
                the `docs/` or `entities/` folders already exist at `root`.
        """
        layout = VaultLayout(root)

        if self.vault_fs.exists(layout.forte_dir):
            raise VaultAlreadyExistsError(
                f"Forte vault already exists at {layout.forte_dir}"
            )

        for conflict in (layout.docs_dir, layout.entities_dir):
            if self.vault_fs.exists(conflict):
                rel = (
                    conflict.relative_to(root)
                    if conflict.is_relative_to(root)
                    else conflict
                )
                raise VaultAlreadyExistsError(
                    f"{rel}/ folder already present. Please run forte init in an empty directory"
                )

        for directory in layout.all_dirs():
            self.vault_fs.make_dirs(directory)

        self.vault_fs.write_default_config(layout.config_path)
        self.vault_fs.init_db(layout.db_path)

        return root.resolve()

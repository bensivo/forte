from pathlib import Path

from forte.interface.vault_fs import IVaultFs
from forte.interface.vault_registry import IVaultRegistry
from forte.model.vault import (
    InvalidVaultNameError,
    NoDefaultVaultError,
    Vault,
    VaultAlreadyRegisteredError,
    VaultLayout,
    VaultNotFoundError,
    VaultTargetConflictError,
    _SLUG_RE,
)

# Shown whenever the user has no default vault selected; both commands are
# valid ways out of the situation.
_NO_DEFAULT_HINT = (
    "No default vault is set. Run 'forte vault create <name> <path>' to create "
    "one, or 'forte vault set-default <name>' to select an existing vault."
)


class VaultService:
    """
    Contains all the operations that can be performed on vaults: creating a
    vault on disk, listing / inspecting / removing registered vaults,
    choosing the default vault, and resolving which vault a command should
    operate on.

    Vaults live anywhere on disk and are tracked in a user-level registry.
    Resolution is registry-based only: there is no walk-up-from-cwd
    discovery, so every command works the same from any directory.
    """

    def __init__(self, vault_registry: IVaultRegistry, vault_fs: IVaultFs):
        self.vault_registry = vault_registry
        self.vault_fs = vault_fs

    def create_vault(self, name: str, path: Path) -> Vault:
        """
        Create a new vault on disk and register it under the given name.

        All validation happens before any write, so a failed creation leaves
        both the filesystem and the registry untouched. The target directory
        itself may already exist (e.g. `forte vault create personal .`) as
        long as it holds no conflicting vault files or folders.

        If no default vault is currently set, the newly created vault becomes
        the default.

        Args:
            name (str): The vault's slug name, used as its registry key.
            path (Path): The directory to create the vault in. Resolved to an
                absolute path before being registered.

        Returns:
            (Vault) The created vault, with its absolute, resolved path.

        Raises:
            InvalidVaultNameError: if the name is not a valid slug
                (`^[a-z0-9][a-z0-9_-]*$`).
            VaultAlreadyRegisteredError: if a vault is already registered
                under this name.
            VaultTargetConflictError: if the target directory already contains
                a `forte.db` or `forte.yaml`, or a `docs/` or `entities/`
                folder.
        """
        if not _SLUG_RE.match(name):
            raise InvalidVaultNameError(
                f"Invalid vault name {name!r}: use lowercase letters, digits, "
                "hyphens, or underscores only (no spaces, slashes, or uppercase)."
            )

        if self.vault_registry.check_exists(name):
            raise VaultAlreadyRegisteredError(
                f"Vault {name!r} is already registered."
            )

        root = Path(path).resolve()
        layout = VaultLayout(root)

        for conflict in (layout.db_path, layout.config_path):
            if self.vault_fs.exists(conflict):
                raise VaultTargetConflictError(
                    f"A Forte vault already exists at {root}: {conflict.name} is present."
                )

        for conflict in (layout.docs_dir, layout.entities_dir):
            if self.vault_fs.exists(conflict):
                raise VaultTargetConflictError(
                    f"{conflict.name}/ folder already present at {root}. "
                    "Create the vault in an empty directory instead."
                )

        # `all_dirs()` never includes the vault root itself, and each entry is
        # created before its children, so an already-existing root directory is
        # fine even though IVaultFs.make_dirs fails on an existing directory.
        for directory in layout.all_dirs():
            self.vault_fs.make_dirs(directory)

        self.vault_fs.write_default_config(layout.config_path)
        self.vault_fs.init_db(layout.db_path)

        vault = Vault(name=name, path=root)
        self.vault_registry.add(vault)

        if self.vault_registry.get_default() is None:
            self.vault_registry.set_default(name)

        return vault

    def list_vaults(self) -> list[Vault]:
        """
        List all registered vaults.

        Returns:
            (list[Vault]) All registered vaults, ordered by name.
        """
        return self.vault_registry.list()

    def get_vault(self, name: str) -> Vault:
        """
        Return a single registered vault by name.

        Args:
            name (str): The name of the vault to look up.

        Returns:
            (Vault) The registered vault.

        Raises:
            VaultNotFoundError: if no vault is registered under this name.
        """
        vault = self.vault_registry.get(name)
        if vault is None:
            raise VaultNotFoundError(f"Vault {name!r} is not registered.")
        return vault

    def remove_vault(self, name: str) -> None:
        """
        Unregister a vault.

        This only removes the vault from the registry — nothing on disk is
        deleted, so the vault's documents, entities, config, and database all
        remain and the vault can be re-registered later. If the removed vault
        was the default, the default is cleared rather than left dangling.

        Args:
            name (str): The name of the vault to unregister.

        Returns:
            None

        Raises:
            VaultNotFoundError: if no vault is registered under this name.
        """
        if not self.vault_registry.check_exists(name):
            raise VaultNotFoundError(f"Vault {name!r} is not registered.")

        was_default = self.vault_registry.get_default() == name

        self.vault_registry.remove(name)

        if was_default:
            self.vault_registry.set_default(None)

    def set_default_vault(self, name: str) -> None:
        """
        Mark a registered vault as the default.

        Args:
            name (str): The name of the vault to make the default.

        Returns:
            None

        Raises:
            VaultNotFoundError: if no vault is registered under this name.
        """
        if not self.vault_registry.check_exists(name):
            raise VaultNotFoundError(f"Vault {name!r} is not registered.")

        self.vault_registry.set_default(name)

    def resolve_vault(self, name: str | None) -> Vault:
        """
        Resolve which vault a command should operate on.

        With a name, that vault is returned. Without one, the default vault is
        returned. There is no walk-up-from-the-current-directory fallback: the
        result does not depend on where the command was run from.

        Args:
            name (str | None): An explicit vault name, or None to use the
                default vault.

        Returns:
            (Vault) The resolved vault.

        Raises:
            NoDefaultVaultError: if `name` is None and no default vault is set.
            VaultNotFoundError: if `name` is given but no vault is registered
                under it, or if the default vault name no longer refers to a
                registered vault.
        """
        if name is not None:
            return self.get_vault(name)

        default_name = self.vault_registry.get_default()
        if default_name is None:
            raise NoDefaultVaultError(_NO_DEFAULT_HINT)

        vault = self.vault_registry.get(default_name)
        if vault is None:
            raise VaultNotFoundError(
                f"The default vault {default_name!r} is no longer registered. "
                "Run 'forte vault set-default <name>' to select another vault."
            )
        return vault

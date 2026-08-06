from abc import ABC, abstractmethod

from forte.model.vault import Vault


class IVaultRegistry(ABC):
    """
    Interface for persisting and querying the user-level registry of known
    vaults: which vault names exist, where each lives on disk, and which
    one (if any) is the default. Implementations handle storage only — no
    validation and no business rules.
    """

    @abstractmethod
    def check_exists(self, name: str) -> bool:
        """
        Check whether a vault with the given name is already registered.

        Args:
            name (str): The vault name to look up.

        Returns:
            (bool) True if a vault with this name is registered.
        """
        pass

    @abstractmethod
    def add(self, vault: Vault) -> None:
        """
        Register a new vault.

        Args:
            vault (Vault): The vault to register.

        Returns:
            None
        """
        pass

    @abstractmethod
    def get(self, name: str) -> Vault | None:
        """
        Return a single registered vault by name.

        Args:
            name (str): The vault name to look up.

        Returns:
            (Vault | None) The vault, or None if no vault is registered
            under this name.
        """
        pass

    @abstractmethod
    def list(self) -> list[Vault]:
        """
        Return all registered vaults, ordered by name.

        Returns:
            (list[Vault]) All registered vaults.
        """
        pass

    @abstractmethod
    def remove(self, name: str) -> None:
        """
        Unregister a vault by name. Does not touch anything on disk.

        Args:
            name (str): The vault name to remove.

        Returns:
            None
        """
        pass

    @abstractmethod
    def get_default(self) -> str | None:
        """
        Return the name of the default vault.

        Returns:
            (str | None) The default vault's name, or None if no default is
            set. Returned as-is even if the name no longer resolves to a
            registered vault.
        """
        pass

    @abstractmethod
    def set_default(self, name: str | None) -> None:
        """
        Mark the given vault name as the default.

        Args:
            name (str | None): The vault name to set as default, or None to
                clear the default so no vault is selected.

        Returns:
            None
        """
        pass

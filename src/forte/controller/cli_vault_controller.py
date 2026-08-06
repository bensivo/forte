from pathlib import Path

import click

from forte.model.vault import VaultError
from forte.service.vault_service import VaultService


class CliVaultController:
    """
    CLI interface for VaultService. Wires VaultService operations up as a
    `vault` Click command group (create/list/show/remove/set-default),
    translating VaultError into Click errors. Contains no business logic of
    its own.
    """

    def __init__(self, vault_service: VaultService):
        """
        Args:
            vault_service (VaultService): The service to call for all vault
                operations.
        """
        self.vault_service = vault_service

    def group(self) -> click.Group:
        """
        Build the `vault` Click command group.

        Returns:
            (click.Group) The `vault` command group, ready to attach to a
                parent Click group.
        """
        controller = self

        @click.group()
        def vault() -> None:
            """Create, inspect, and manage the registry of Forte vaults."""

        @vault.command("create")
        @click.argument("name")
        @click.argument("path")
        def vault_create(name: str, path: str) -> None:
            """Create a new vault named NAME at PATH and register it."""
            controller._create(name, path)

        @vault.command("list")
        def vault_list() -> None:
            """List all registered vaults."""
            controller._list()

        @vault.command("show")
        @click.argument("name")
        def vault_show(name: str) -> None:
            """Show details of the vault NAME."""
            controller._show(name)

        @vault.command("remove")
        @click.argument("name")
        @click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt.")
        def vault_remove(name: str, yes: bool) -> None:
            """Unregister the vault NAME.

            This only removes NAME from the vault registry — it never deletes
            forte.db, forte.yaml, or any files under the vault's directory on
            disk.
            """
            controller._remove(name, yes)

        @vault.command("set-default")
        @click.argument("name")
        def vault_set_default(name: str) -> None:
            """Make the vault NAME the default vault."""
            controller._set_default(name)

        return vault

    def _create(self, name: str, path: str) -> None:
        try:
            created = self.vault_service.create_vault(name, Path(path))
        except VaultError as e:
            raise click.ClickException(str(e))

        click.echo(f"Created vault '{created.name}' at {created.path}")

    def _list(self) -> None:
        try:
            vaults = self.vault_service.list_vaults()
        except VaultError as e:
            raise click.ClickException(str(e))

        if not vaults:
            click.echo("No vaults registered yet. Run 'forte vault create <name> <path>' to create one.")
            return

        default_name = self._default_name()
        for v in vaults:
            marker = " (default)" if v.name == default_name else ""
            click.echo(f"{v.name}: {v.path}{marker}")

    def _show(self, name: str) -> None:
        try:
            v = self.vault_service.get_vault(name)
        except VaultError as e:
            raise click.ClickException(str(e))

        default_name = self._default_name()
        is_default = v.name == default_name

        click.echo(f"Name: {v.name}")
        click.echo(f"Path: {v.path}")
        click.echo(f"Default: {'yes' if is_default else 'no'}")

    def _remove(self, name: str, yes: bool) -> None:
        if not yes and not click.confirm(f"Remove vault '{name}'?"):
            click.echo("Aborted.")
            return

        try:
            self.vault_service.remove_vault(name)
        except VaultError as e:
            raise click.ClickException(str(e))

        click.echo(f"Removed vault '{name}'. Files on disk are untouched.")

    def _set_default(self, name: str) -> None:
        try:
            self.vault_service.set_default_vault(name)
        except VaultError as e:
            raise click.ClickException(str(e))

        click.echo(f"'{name}' is now the default vault.")

    def _default_name(self) -> str | None:
        """
        Best-effort lookup of the current default vault's name, used to mark
        the default in `list`/`show` output. VaultService has no direct
        "is this the default" query, so this resolves via
        `resolve_vault(None)` and treats the "no default set" case as "no
        vault is marked" rather than an error.

        Returns:
            (str | None) The default vault's name, or None if no default is
                set.
        """
        try:
            return self.vault_service.resolve_vault(None).name
        except VaultError:
            return None

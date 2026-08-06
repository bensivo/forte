import click

from forte.model.schema import SchemaError
from forte.model.vault import VaultContext, VaultError
from forte.service.schema_service import SchemaService
from forte.service.vault_service import VaultService


# Adds the shared `--vault <name>` selector to a schema subcommand. Defined
# once so every subcommand spells the option identically.
def _vault_option(f):
    return click.option(
        "--vault",
        "vault_name",
        default=None,
        help="Name of the vault to operate on (defaults to the default vault).",
    )(f)


class CliSchemaController:
    """
    CLI interface for SchemaService. Wires SchemaService operations up as a
    `schema` Click command group (add/list/remove), translating SchemaError
    and VaultError into Click errors. Contains no business logic of its own.

    Vault selection: `--vault <name>` is a per-subcommand option, so it is
    written after the subcommand (`forte schema list --vault work`). The same
    placement is used by the `entity` and `doc` groups. Each subcommand
    resolves the named vault (or the default vault when the option is
    omitted) and points the shared VaultContext at it before calling the
    service, so results never depend on the current working directory.
    """

    def __init__(
        self,
        schema_service: SchemaService,
        vault_service: VaultService,
        vault_context: VaultContext,
    ):
        """
        Args:
            schema_service (SchemaService): The service to call for all schema operations.
            vault_service (VaultService): The service used to resolve which vault
                a subcommand operates on.
            vault_context (VaultContext): The shared context the resolved vault
                root is written to before each service call.
        """
        self.schema_service = schema_service
        self.vault_service = vault_service
        self.vault_context = vault_context

    def group(self) -> click.Group:
        """
        Build the `schema` Click command group.

        Returns:
            (click.Group) The `schema` command group, ready to attach to a
                parent Click group.
        """
        controller = self

        @click.group()
        def schema() -> None:
            """Define, inspect, and remove entity schemas in a vault."""

        @schema.command("add")
        @click.argument("name")
        @click.option("--field", "fields", multiple=True, help="A field name (repeatable).")
        @_vault_option
        def schema_add(name: str, fields: tuple[str, ...], vault_name: str | None) -> None:
            """Add a schema NAME with zero or more --field options."""
            controller._add(name, list(fields), vault_name)

        @schema.command("list")
        @_vault_option
        def schema_list(vault_name: str | None) -> None:
            """List all schemas defined in the vault."""
            controller._list(vault_name)

        @schema.command("remove")
        @click.argument("name")
        @click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt.")
        @_vault_option
        def schema_remove(name: str, yes: bool, vault_name: str | None) -> None:
            """Remove the schema NAME from the vault."""
            controller._remove(name, yes, vault_name)

        return schema

    def _select_vault(self, vault_name: str | None) -> None:
        """
        Point the shared VaultContext at the vault this invocation targets.

        Args:
            vault_name (str | None): An explicit vault name from `--vault`, or
                None to use the default vault.

        Returns:
            None

        Raises:
            VaultError: if the named vault is not registered, or no name was
                given and no default vault is set.
        """
        vault = self.vault_service.resolve_vault(vault_name)
        self.vault_context.set_root(vault.path)

    def _add(self, name: str, fields: list[str], vault_name: str | None) -> None:
        try:
            self._select_vault(vault_name)
            created = self.schema_service.create_schema(name, fields)
        except (SchemaError, VaultError) as e:
            raise click.ClickException(str(e))

        field_names = [f.name for f in created.fields]
        if field_names:
            click.echo(f"Added schema '{created.name}' with fields: {', '.join(field_names)}")
        else:
            click.echo(f"Added schema '{created.name}' (no fields)")

    def _list(self, vault_name: str | None) -> None:
        try:
            self._select_vault(vault_name)
            schemas = self.schema_service.list_schemas()
        except (SchemaError, VaultError) as e:
            raise click.ClickException(str(e))

        if not schemas:
            click.echo("No schemas defined yet.")
            return

        for s in schemas:
            field_names = [f.name for f in s.fields]
            if field_names:
                click.echo(f"{s.name}: {', '.join(field_names)}")
            else:
                click.echo(f"{s.name} (no fields)")

    def _remove(self, name: str, yes: bool, vault_name: str | None) -> None:
        if not yes and not click.confirm(f"Remove schema '{name}'?"):
            click.echo("Aborted.")
            return

        try:
            self._select_vault(vault_name)
            self.schema_service.remove_schema(name)
        except (SchemaError, VaultError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Removed schema '{name}'.")

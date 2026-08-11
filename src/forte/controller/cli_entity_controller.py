import click

from forte.model.entity import EntityError
from forte.model.vault import VaultContext, VaultError
from forte.service.entity_service import EntityService
from forte.service.vault_service import VaultService


def _parse_field_option(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        raise click.ClickException(
            f"Invalid --field {raw!r}: expected key=value."
        )
    key, _, value = raw.partition("=")
    return key, value


# Adds the shared `--vault <name>` selector to an entity subcommand. Defined
# once so every subcommand spells the option identically.
def _vault_option(f):
    return click.option(
        "--vault",
        "vault_name",
        default=None,
        help="Name of the vault to operate on (defaults to the default vault).",
    )(f)


class CliEntityController:
    """
    CLI interface for EntityService. Wires EntityService operations up as an
    `entity` Click command group (add/list/show/edit/remove), translating
    EntityError and VaultError into Click errors. Contains no business logic
    of its own.

    Vault selection: `--vault <name>` is a per-subcommand option, so it is
    written after the subcommand (`forte entity list --vault work`). The same
    placement is used by the `schema` and `doc` groups. Each subcommand
    resolves the named vault (or the default vault when the option is
    omitted) and points the shared VaultContext at it before calling the
    service, so results never depend on the current working directory.
    """

    def __init__(
        self,
        entity_service: EntityService,
        vault_service: VaultService,
        vault_context: VaultContext,
    ):
        """
        Args:
            entity_service (EntityService): The service to call for all
                entity operations.
            vault_service (VaultService): The service used to resolve which vault
                a subcommand operates on.
            vault_context (VaultContext): The shared context the resolved vault
                root is written to before each service call.
        """
        self.entity_service = entity_service
        self.vault_service = vault_service
        self.vault_context = vault_context

    def group(self) -> click.Group:
        """
        Build the `entity` Click command group.

        Returns:
            (click.Group) The `entity` command group, ready to attach to a
                parent Click group.
        """
        controller = self

        @click.group()
        def entity() -> None:
            """Add, inspect, edit, and remove entities in a vault."""

        @entity.command("add")
        @click.argument("schema")
        @click.option("--name", required=True, help="The entity's name.")
        @click.option("--alias", "aliases", multiple=True, help="An alias (repeatable).")
        @click.option(
            "--field", "fields", multiple=True, help="A field=value pair (repeatable)."
        )
        @_vault_option
        def entity_add(
            schema: str,
            name: str,
            aliases: tuple[str, ...],
            fields: tuple[str, ...],
            vault_name: str | None,
        ) -> None:
            """Add an entity of SCHEMA with --name, --alias(es), and --field(s)."""
            field_values = dict(_parse_field_option(f) for f in fields)
            controller._add(schema, name, list(aliases), field_values, vault_name)

        @entity.command("list")
        @click.option("--schema", default=None, help="Only list entities of this schema.")
        @_vault_option
        def entity_list(schema: str | None, vault_name: str | None) -> None:
            """List entities in the vault, optionally filtered by --schema."""
            controller._list(schema, vault_name)

        @entity.command("show")
        @click.argument("id", type=int)
        @_vault_option
        def entity_show(id: int, vault_name: str | None) -> None:
            """Show the entity with ID."""
            controller._show(id, vault_name)

        @entity.command("edit")
        @click.argument("id", type=int)
        @click.option("--name", default=None, help="New name for the entity.")
        @click.option("--set", "set_fields", multiple=True, help="A field=value pair (repeatable).")
        @click.option("--add-alias", "add_aliases", multiple=True, help="An alias to add (repeatable).")
        @click.option(
            "--remove-alias", "remove_aliases", multiple=True, help="An alias to remove (repeatable)."
        )
        @_vault_option
        def entity_edit(
            id: int,
            name: str | None,
            set_fields: tuple[str, ...],
            add_aliases: tuple[str, ...],
            remove_aliases: tuple[str, ...],
            vault_name: str | None,
        ) -> None:
            """Edit the entity with ID."""
            field_values = dict(_parse_field_option(f) for f in set_fields)
            controller._edit(
                id, name, field_values, list(add_aliases), list(remove_aliases), vault_name
            )

        @entity.command("remove")
        @click.argument("id", type=int)
        @click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt.")
        @_vault_option
        def entity_remove(id: int, yes: bool, vault_name: str | None) -> None:
            """Remove the entity with ID."""
            controller._remove(id, yes, vault_name)

        return entity

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

    def _add(
        self,
        schema: str,
        name: str,
        aliases: list[str],
        field_values: dict[str, str],
        vault_name: str | None,
    ) -> None:
        try:
            self._select_vault(vault_name)
            created = self.entity_service.add_entity(
                schema, name, aliases=aliases, field_values=field_values
            )
        except (EntityError, VaultError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Added entity '{created.name}' (#{created.id}) of schema '{schema}'")

    def _list(self, schema: str | None, vault_name: str | None) -> None:
        try:
            self._select_vault(vault_name)
            entities = self.entity_service.list_entities(schema=schema)
        except (EntityError, VaultError) as e:
            raise click.ClickException(str(e))

        if not entities:
            click.echo("No entities yet.")
            return

        for e in entities:
            click.echo(f"#{e.id} [{e.schema}] {e.name}")

    def _show(self, id: int, vault_name: str | None) -> None:
        try:
            self._select_vault(vault_name)
            entity = self.entity_service.get_entity(id)
            mentioning_docs = self.entity_service.list_mentioning_documents(id)
        except (EntityError, VaultError) as e:
            raise click.ClickException(str(e))

        click.echo(f"#{entity.id} {entity.name} ({entity.schema})")
        click.echo(f"Aliases: {', '.join(entity.aliases) or '(none)'}")
        for key, value in entity.fields.items():
            click.echo(f"{key}: {value}")

        click.echo("")
        if mentioning_docs:
            click.echo("Mentions:")
            for doc in mentioning_docs:
                click.echo(f"  doc #{doc.id} {doc.name}")
        else:
            click.echo("Mentions: (none)")

    def _edit(
        self,
        id: int,
        name: str | None,
        set_fields: dict[str, str],
        add_aliases: list[str],
        remove_aliases: list[str],
        vault_name: str | None,
    ) -> None:
        try:
            self._select_vault(vault_name)
            self.entity_service.edit_entity(
                id,
                name=name,
                set_fields=set_fields,
                add_aliases=add_aliases,
                remove_aliases=remove_aliases,
            )
        except (EntityError, VaultError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Updated entity #{id}.")

    def _remove(self, id: int, yes: bool, vault_name: str | None) -> None:
        if not yes and not click.confirm(f"Remove entity #{id}?"):
            click.echo("Aborted.")
            return

        try:
            self._select_vault(vault_name)
            self.entity_service.remove_entity(id)
        except (EntityError, VaultError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Removed entity #{id}.")

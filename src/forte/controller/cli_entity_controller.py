import click

from forte.model.entity import EntityError
from forte.service.entity_service import EntityService
from forte.services.discovery import VaultNotFoundError


def _parse_field_option(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        raise click.ClickException(
            f"Invalid --field {raw!r}: expected key=value."
        )
    key, _, value = raw.partition("=")
    return key, value


class CliEntityController:
    """
    CLI interface for EntityService. Wires EntityService operations up as an
    `entity` Click command group (add/list/show/edit/remove), translating
    EntityError and VaultNotFoundError into Click errors. Contains no
    business logic of its own.
    """

    def __init__(self, entity_service: EntityService):
        """
        Args:
            entity_service (EntityService): The service to call for all
                entity operations.
        """
        self.entity_service = entity_service

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
        def entity_add(schema: str, name: str, aliases: tuple[str, ...], fields: tuple[str, ...]) -> None:
            """Add an entity of SCHEMA with --name, --alias(es), and --field(s)."""
            field_values = dict(_parse_field_option(f) for f in fields)
            controller._add(schema, name, list(aliases), field_values)

        @entity.command("list")
        @click.option("--schema", default=None, help="Only list entities of this schema.")
        def entity_list(schema: str | None) -> None:
            """List entities in the vault, optionally filtered by --schema."""
            controller._list(schema)

        @entity.command("show")
        @click.argument("id", type=int)
        def entity_show(id: int) -> None:
            """Show the entity with ID."""
            controller._show(id)

        @entity.command("edit")
        @click.argument("id", type=int)
        @click.option("--name", default=None, help="New name for the entity.")
        @click.option("--set", "set_fields", multiple=True, help="A field=value pair (repeatable).")
        @click.option("--add-alias", "add_aliases", multiple=True, help="An alias to add (repeatable).")
        @click.option(
            "--remove-alias", "remove_aliases", multiple=True, help="An alias to remove (repeatable)."
        )
        def entity_edit(
            id: int,
            name: str | None,
            set_fields: tuple[str, ...],
            add_aliases: tuple[str, ...],
            remove_aliases: tuple[str, ...],
        ) -> None:
            """Edit the entity with ID."""
            field_values = dict(_parse_field_option(f) for f in set_fields)
            controller._edit(id, name, field_values, list(add_aliases), list(remove_aliases))

        @entity.command("remove")
        @click.argument("id", type=int)
        @click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt.")
        def entity_remove(id: int, yes: bool) -> None:
            """Remove the entity with ID."""
            controller._remove(id, yes)

        return entity

    def _add(
        self, schema: str, name: str, aliases: list[str], field_values: dict[str, str]
    ) -> None:
        try:
            created = self.entity_service.add_entity(
                schema, name, aliases=aliases, field_values=field_values
            )
        except (EntityError, VaultNotFoundError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Added entity '{created.name}' (#{created.id}) of schema '{schema}'")

    def _list(self, schema: str | None) -> None:
        try:
            entities = self.entity_service.list_entities(schema=schema)
        except (EntityError, VaultNotFoundError) as e:
            raise click.ClickException(str(e))

        if not entities:
            click.echo("No entities yet.")
            return

        for e in entities:
            click.echo(f"#{e.id} [{e.schema}] {e.name}")

    def _show(self, id: int) -> None:
        try:
            entity = self.entity_service.get_entity(id)
        except (EntityError, VaultNotFoundError) as e:
            raise click.ClickException(str(e))

        click.echo(f"#{entity.id} {entity.name} ({entity.schema})")
        click.echo(f"Aliases: {', '.join(entity.aliases) or '(none)'}")
        for key, value in entity.fields.items():
            click.echo(f"{key}: {value}")

    def _edit(
        self,
        id: int,
        name: str | None,
        set_fields: dict[str, str],
        add_aliases: list[str],
        remove_aliases: list[str],
    ) -> None:
        try:
            self.entity_service.edit_entity(
                id,
                name=name,
                set_fields=set_fields,
                add_aliases=add_aliases,
                remove_aliases=remove_aliases,
            )
        except (EntityError, VaultNotFoundError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Updated entity #{id}.")

    def _remove(self, id: int, yes: bool) -> None:
        if not yes and not click.confirm(f"Remove entity #{id}?"):
            click.echo("Aborted.")
            return

        try:
            self.entity_service.remove_entity(id)
        except (EntityError, VaultNotFoundError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Removed entity #{id}.")

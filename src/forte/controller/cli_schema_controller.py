import click

from forte.model.schema import SchemaError
from forte.service.schema_service import SchemaService


class CliSchemaController:
    """
    CLI interface for SchemaService. Wires SchemaService operations up as a
    `schema` Click command group (add/list/remove), translating SchemaError
    subclasses into Click errors. Contains no business logic of its own.
    """

    def __init__(self, schema_service: SchemaService):
        """
        Args:
            schema_service (SchemaService): The service to call for all schema operations.
        """
        self.schema_service = schema_service

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
        def schema_add(name: str, fields: tuple[str, ...]) -> None:
            """Add a schema NAME with zero or more --field options."""
            controller._add(name, list(fields))

        @schema.command("list")
        def schema_list() -> None:
            """List all schemas defined in the vault."""
            controller._list()

        @schema.command("remove")
        @click.argument("name")
        @click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt.")
        def schema_remove(name: str, yes: bool) -> None:
            """Remove the schema NAME from the vault."""
            controller._remove(name, yes)

        return schema

    def _add(self, name: str, fields: list[str]) -> None:
        try:
            created = self.schema_service.create_schema(name, fields)
        except SchemaError as e:
            raise click.ClickException(str(e))

        field_names = [f.name for f in created.fields]
        if field_names:
            click.echo(f"Added schema '{created.name}' with fields: {', '.join(field_names)}")
        else:
            click.echo(f"Added schema '{created.name}' (no fields)")

    def _list(self) -> None:
        schemas = self.schema_service.list_schemas()
        if not schemas:
            click.echo("No schemas defined yet.")
            return

        for s in schemas:
            field_names = [f.name for f in s.fields]
            if field_names:
                click.echo(f"{s.name}: {', '.join(field_names)}")
            else:
                click.echo(f"{s.name} (no fields)")

    def _remove(self, name: str, yes: bool) -> None:
        if not yes and not click.confirm(f"Remove schema '{name}'?"):
            click.echo("Aborted.")
            return

        try:
            self.schema_service.remove_schema(name)
        except SchemaError as e:
            raise click.ClickException(str(e))

        click.echo(f"Removed schema '{name}'.")

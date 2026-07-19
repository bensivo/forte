"""Driver layer: CLI entry points. No business logic — call into services only."""

from pathlib import Path

import click

from forte.services.discovery import VaultNotFoundError, find_vault_root
from forte.services.entity import (
    EntityError,
    add_entity,
    edit_entity,
    get_entity,
    list_entities,
    remove_entity,
)
from forte.services.init import VaultAlreadyExistsError
from forte.services.init import init as init_vault
from forte.services.schema import (
    SchemaError,
    add_schema,
    list_schemas,
    remove_schema,
)


def _parse_key_value(token: str) -> tuple[str, str]:
    """Parse a ``key=value`` token, splitting on the first ``=`` only.

    The value may itself contain ``=``. A token with no ``=`` is a usage error.
    """
    if "=" not in token:
        raise click.BadParameter(f"Expected 'key=value', got {token!r} (missing '=').")
    key, value = token.split("=", 1)
    return key, value


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Forte CLI."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command()
def init() -> None:
    """Initialize a new Forte vault in the current directory."""
    try:
        root = init_vault(Path.cwd())
    except VaultAlreadyExistsError as e:
        raise click.ClickException(str(e))
    click.echo(f"Initialized Forte vault in {root}")


@main.group()
def schema() -> None:
    """Define, inspect, and remove entity schemas in a vault."""


@schema.command("add")
@click.argument("name")
@click.option("--field", "fields", multiple=True, help="A field name (repeatable).")
def schema_add(name: str, fields: tuple[str, ...]) -> None:
    """Add a schema NAME with zero or more --field options."""
    try:
        root = find_vault_root(Path.cwd())
    except VaultNotFoundError as e:
        raise click.ClickException(str(e))

    try:
        created = add_schema(root, name, list(fields))
    except SchemaError as e:
        raise click.ClickException(str(e))

    if created.fields:
        click.echo(f"Added schema '{created.name}' with fields: {', '.join(created.fields)}")
    else:
        click.echo(f"Added schema '{created.name}' (no fields)")


@schema.command("list")
def schema_list() -> None:
    """List all schemas defined in the vault."""
    try:
        root = find_vault_root(Path.cwd())
    except VaultNotFoundError as e:
        raise click.ClickException(str(e))

    schemas = list_schemas(root)
    if not schemas:
        click.echo("No schemas defined yet.")
        return

    for s in schemas:
        if s.fields:
            click.echo(f"{s.name}: {', '.join(s.fields)}")
        else:
            click.echo(f"{s.name} (no fields)")


@schema.command("remove")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt.")
def schema_remove(name: str, yes: bool) -> None:
    """Remove the schema NAME from the vault."""
    try:
        root = find_vault_root(Path.cwd())
    except VaultNotFoundError as e:
        raise click.ClickException(str(e))

    if not yes and not click.confirm(f"Remove schema '{name}'?"):
        click.echo("Aborted.")
        return

    try:
        remove_schema(root, name)
    except SchemaError as e:
        raise click.ClickException(str(e))

    click.echo(f"Removed schema '{name}'.")


@main.group()
def entity() -> None:
    """Create, inspect, edit, and remove entities in a vault."""


@entity.command("add")
@click.argument("schema")
@click.option("--name", required=True, help="The entity's name (required).")
@click.option("--alias", "aliases", multiple=True, help="An alias (repeatable).")
@click.option(
    "--field",
    "fields",
    multiple=True,
    help="A field value as key=value (repeatable).",
)
def entity_add(schema: str, name: str, aliases: tuple[str, ...], fields: tuple[str, ...]) -> None:
    """Add an entity of SCHEMA with a name, optional aliases and fields."""
    try:
        root = find_vault_root(Path.cwd())
    except VaultNotFoundError as e:
        raise click.ClickException(str(e))

    field_values = dict(_parse_key_value(f) for f in fields)

    try:
        created = add_entity(
            root,
            schema,
            name,
            aliases=list(aliases),
            field_values=field_values,
        )
    except EntityError as e:
        raise click.ClickException(str(e))

    click.echo(f"Added {created.schema} entity #{created.id}: {created.name}")


@entity.command("list")
@click.option("--schema", "schema", default=None, help="Filter to a single schema.")
def entity_list(schema: str | None) -> None:
    """List entities, optionally filtered by --schema."""
    try:
        root = find_vault_root(Path.cwd())
    except VaultNotFoundError as e:
        raise click.ClickException(str(e))

    try:
        entities = list_entities(root, schema=schema)
    except EntityError as e:
        raise click.ClickException(str(e))

    if not entities:
        click.echo("No entities yet.")
        return

    for ent in entities:
        click.echo(f"#{ent.id}\t{ent.schema}\t{ent.name}")


@entity.command("show")
@click.argument("id", type=int)
def entity_show(id: int) -> None:
    """Show a single entity by ID."""
    try:
        root = find_vault_root(Path.cwd())
    except VaultNotFoundError as e:
        raise click.ClickException(str(e))

    try:
        ent = get_entity(root, id)
    except EntityError as e:
        raise click.ClickException(str(e))

    click.echo(f"#{ent.id} [{ent.schema}] {ent.name}")
    aliases = ", ".join(ent.aliases) if ent.aliases else "(none)"
    click.echo(f"Aliases: {aliases}")
    for key, value in ent.fields.items():
        click.echo(f"{key}: {value}")
    if ent.body:
        click.echo("")
        click.echo(ent.body)


@entity.command("edit")
@click.argument("id", type=int)
@click.option("--name", default=None, help="Rename the entity.")
@click.option(
    "--set",
    "set_fields",
    multiple=True,
    help="Set a schema field as key=value (repeatable).",
)
@click.option("--add-alias", "add_aliases", multiple=True, help="Add an alias (repeatable).")
@click.option(
    "--remove-alias",
    "remove_aliases",
    multiple=True,
    help="Remove an alias (repeatable).",
)
def entity_edit(
    id: int,
    name: str | None,
    set_fields: tuple[str, ...],
    add_aliases: tuple[str, ...],
    remove_aliases: tuple[str, ...],
) -> None:
    """Edit an entity's name, fields, and aliases."""
    try:
        root = find_vault_root(Path.cwd())
    except VaultNotFoundError as e:
        raise click.ClickException(str(e))

    parsed_fields = dict(_parse_key_value(f) for f in set_fields)

    try:
        updated = edit_entity(
            root,
            id,
            name=name,
            set_fields=parsed_fields,
            add_aliases=list(add_aliases),
            remove_aliases=list(remove_aliases),
        )
    except EntityError as e:
        raise click.ClickException(str(e))

    click.echo(f"Updated {updated.schema} entity #{updated.id}: {updated.name}")


@entity.command("remove")
@click.argument("id", type=int)
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt.")
def entity_remove(id: int, yes: bool) -> None:
    """Remove the entity with the given ID."""
    try:
        root = find_vault_root(Path.cwd())
    except VaultNotFoundError as e:
        raise click.ClickException(str(e))

    if not yes and not click.confirm(f"Remove entity #{id}?"):
        click.echo("Aborted.")
        return

    try:
        remove_entity(root, id)
    except EntityError as e:
        raise click.ClickException(str(e))

    click.echo(f"Removed entity #{id}.")

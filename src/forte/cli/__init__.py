"""Driver layer: CLI entry points. No business logic — call into services only."""

from pathlib import Path

import click

from forte.services.discovery import VaultNotFoundError, find_vault_root
from forte.services.init import VaultAlreadyExistsError
from forte.services.init import init as init_vault
from forte.services.schema import (
    SchemaError,
    add_schema,
    list_schemas,
    remove_schema,
)


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
        click.echo(
            f"Added schema '{created.name}' with fields: {', '.join(created.fields)}"
        )
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

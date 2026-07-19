"""Driver layer: CLI entry points. No business logic — call into services only."""

from pathlib import Path

import click

from forte.services.init import VaultAlreadyExistsError, init as init_vault


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

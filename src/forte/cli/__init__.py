"""Driver layer: CLI entry points."""

from pathlib import Path

import click

from forte.db.schema import initialize_database
from forte.domain.vault import VaultLayout
from forte.services.config import write_default_config


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Forte CLI."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command()
def init() -> None:
    """Initialize a new Forte vault in the current directory."""
    root = Path.cwd()
    layout = VaultLayout(root)

    if layout.forte_dir.exists():
        raise click.ClickException(f"Forte vault already exists at {layout.forte_dir}")

    for directory in layout.all_dirs():
        directory.mkdir(parents=True)

    write_default_config(layout.config_path)
    initialize_database(layout.db_path)

    click.echo(f"Initialized Forte vault in {root.resolve()}")

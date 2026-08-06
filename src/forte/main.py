"""Composition root: wires clients, services, and controllers, and exposes
the top-level Click CLI.
"""

import sqlite3
from pathlib import Path

import click

from forte.client.fs_vault_fs import LocalVaultFs
from forte.client.sqlite_schema_db import SqliteSchemaDb
from forte.controller.cli_init_controller import CliInitController
from forte.controller.cli_schema_controller import CliSchemaController
from forte.service.init_service import InitService
from forte.service.schema_service import SchemaService
from forte.services.discovery import VaultNotFoundError, find_vault_root

@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Forte CLI."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# init: no vault dependency, so it's always wired and attached.
init_vault_fs = LocalVaultFs()
init_service = InitService(init_vault_fs)
init_controller = CliInitController(init_service)
main.add_command(init_controller.command())


# schema: only wired if a vault is found from the current directory.
try:
    _root = find_vault_root(Path.cwd())
except VaultNotFoundError:
    _root = None

if _root is not None:
    conn = sqlite3.connect(_root / ".forte" / "index.db")
    schema_db = SqliteSchemaDb(conn, _root)
    schema_service = SchemaService(schema_db)
    schema_controller = CliSchemaController(schema_service)
    main.add_command(schema_controller.group())
else:
    @main.group("schema", invoke_without_command=True)
    def _schema_unavailable() -> None:
        """Define, inspect, and remove entity schemas in a vault."""
        raise click.ClickException(
            "Not inside a Forte vault (no .forte/ directory found). Run 'forte init' first."
        )


if __name__ == "__main__":
    main()

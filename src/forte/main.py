"""Composition root: wires clients, services, and controllers, and exposes
the top-level Click CLI.
"""

import click

from forte.client.fs_vault_fs import LocalVaultFs
from forte.client.sqlite_schema_db import SqliteSchemaDb
from forte.controller.cli_init_controller import CliInitController
from forte.controller.cli_schema_controller import CliSchemaController
from forte.service.init_service import InitService
from forte.service.schema_service import SchemaService


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Forte CLI."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# Add the 'init' command and service
init_vault_fs = LocalVaultFs()
init_service = InitService(init_vault_fs)
init_controller = CliInitController(init_service)
main.add_command(init_controller.command())

# Add the 'schema' sub-commands
schema_db = SqliteSchemaDb()
schema_service = SchemaService(schema_db)
schema_controller = CliSchemaController(schema_service)
main.add_command(schema_controller.group())


if __name__ == "__main__":
    main()

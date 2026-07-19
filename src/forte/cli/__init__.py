"""Driver layer: CLI entry points."""

import click


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Forte CLI."""
    if ctx.invoked_subcommand is None:
        click.echo("hello-world")

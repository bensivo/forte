from pathlib import Path

import click

from forte.model.vault import VaultAlreadyExistsError
from forte.service.init_service import InitService


class CliInitController:
    """
    CLI interface for InitService. Wires InitService operations up as the
    `init` Click command, translating VaultAlreadyExistsError into a Click
    error. Contains no business logic of its own.
    """

    def __init__(self, init_service: InitService):
        """
        Args:
            init_service (InitService): The service to call for all vault
                initialization operations.
        """
        self.init_service = init_service

    def command(self) -> click.Command:
        """
        Build the `init` Click command.

        Returns:
            (click.Command) The `init` command, ready to attach to a parent
                Click group.
        """
        controller = self

        @click.command("init")
        def init() -> None:
            """Initialize a new Forte vault in the current directory."""
            controller._init()

        return init

    def _init(self) -> None:
        try:
            root = self.init_service.init_vault(Path.cwd())
        except VaultAlreadyExistsError as e:
            raise click.ClickException(str(e))

        click.echo(f"Initialized Forte vault in {root}")

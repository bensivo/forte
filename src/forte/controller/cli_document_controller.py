from pathlib import Path

import click

from forte.model.document import DocumentError
from forte.model.entity import EntityError
from forte.service.document_service import DocumentService
from forte.services.discovery import VaultNotFoundError


class CliDocumentController:
    """
    CLI interface for DocumentService. Wires DocumentService operations up as
    a `doc` Click command group (ingest/list/show/link/unlink/remove),
    translating DocumentError, EntityError, and VaultNotFoundError into Click
    errors. Contains no business logic of its own.
    """

    def __init__(self, document_service: DocumentService):
        """
        Args:
            document_service (DocumentService): The service to call for all
                document operations.
        """
        self.document_service = document_service

    def group(self) -> click.Group:
        """
        Build the `doc` Click command group.

        Returns:
            (click.Group) The `doc` command group, ready to attach to a
                parent Click group.
        """
        controller = self

        @click.group()
        def doc() -> None:
            """Ingest and browse documents in a vault."""

        @doc.command("ingest")
        @click.argument("path", type=click.Path(exists=False))
        @click.option(
            "--name", default=None, help="Human-readable name for the doc (defaults to filename)."
        )
        def doc_ingest(path: str, name: str | None) -> None:
            """Ingest the file at PATH into the vault."""
            controller._ingest(path, name)

        @doc.command("list")
        def doc_list() -> None:
            """List all documents in the vault."""
            controller._list()

        @doc.command("show")
        @click.argument("id", type=int)
        def doc_show(id: int) -> None:
            """Show a single document by ID."""
            controller._show(id)

        @doc.command("link")
        @click.argument("id", type=int)
        @click.argument("entity_id", type=int)
        def doc_link(id: int, entity_id: int) -> None:
            """Link document ID to entity ENTITY_ID."""
            controller._link(id, entity_id)

        @doc.command("unlink")
        @click.argument("id", type=int)
        @click.argument("entity_id", type=int)
        def doc_unlink(id: int, entity_id: int) -> None:
            """Unlink document ID from entity ENTITY_ID."""
            controller._unlink(id, entity_id)

        @doc.command("remove")
        @click.argument("id", type=int)
        @click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt.")
        def doc_remove(id: int, yes: bool) -> None:
            """Remove the document with the given ID."""
            controller._remove(id, yes)

        return doc

    def _ingest(self, path: str, name: str | None) -> None:
        try:
            document = self.document_service.ingest_document(Path(path), name=name)
        except (DocumentError, VaultNotFoundError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Ingested doc #{document.id}: {document.name}")

    def _list(self) -> None:
        try:
            documents = self.document_service.list_documents()
        except VaultNotFoundError as e:
            raise click.ClickException(str(e))

        if not documents:
            click.echo("No documents yet.")
            return

        for d in documents:
            click.echo(f"#{d.id}  {d.name}")

    def _show(self, id: int) -> None:
        try:
            document = self.document_service.get_document(id)
        except (DocumentError, VaultNotFoundError) as e:
            raise click.ClickException(str(e))

        click.echo(f"#{document.id} {document.name}")
        click.echo(f"Source: {document.source_path}")
        click.echo(f"Ingested: {document.ingested_at}")
        click.echo(f"Status: {document.status}")

    def _link(self, id: int, entity_id: int) -> None:
        try:
            self.document_service.link_document(id, entity_id)
        except (DocumentError, EntityError, VaultNotFoundError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Linked doc #{id} to entity #{entity_id}")

    def _unlink(self, id: int, entity_id: int) -> None:
        try:
            self.document_service.unlink_document(id, entity_id)
        except (DocumentError, EntityError, VaultNotFoundError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Unlinked doc #{id} from entity #{entity_id}")

    def _remove(self, id: int, yes: bool) -> None:
        try:
            document = self.document_service.get_document(id)
        except (DocumentError, VaultNotFoundError) as e:
            raise click.ClickException(str(e))

        if not yes and not click.confirm(f"Remove doc #{id}: {document.name}?"):
            click.echo("Aborted.")
            return

        try:
            self.document_service.remove_document(id)
        except (DocumentError, VaultNotFoundError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Removed doc #{id}: {document.name}")

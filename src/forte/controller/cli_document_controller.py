from pathlib import Path

import click

from forte.model.document import DocumentError
from forte.model.editor import EditorError
from forte.model.entity import EntityError
from forte.model.vault import VaultContext, VaultError
from forte.service.document_service import DocumentService
from forte.service.vault_service import VaultService


# Adds the shared `--vault <name>` selector to a doc subcommand. Defined once
# so every subcommand spells the option identically.
def _vault_option(f):
    return click.option(
        "--vault",
        "vault_name",
        default=None,
        help="Name of the vault to operate on (defaults to the default vault).",
    )(f)


class CliDocumentController:
    """
    CLI interface for DocumentService. Wires DocumentService operations up as
    a `doc` Click command group (ingest/create/list/show/link/unlink/remove),
    translating DocumentError, EntityError, and VaultError into Click errors.
    Contains no business logic of its own.

    Vault selection: `--vault <name>` is a per-subcommand option, so it is
    written after the subcommand (`forte doc list --vault work`). The same
    placement is used by the `schema` and `entity` groups. Each subcommand
    resolves the named vault (or the default vault when the option is
    omitted) and points the shared VaultContext at it before calling the
    service, so results never depend on the current working directory.
    """

    def __init__(
        self,
        document_service: DocumentService,
        vault_service: VaultService,
        vault_context: VaultContext,
    ):
        """
        Args:
            document_service (DocumentService): The service to call for all
                document operations.
            vault_service (VaultService): The service used to resolve which vault
                a subcommand operates on.
            vault_context (VaultContext): The shared context the resolved vault
                root is written to before each service call.
        """
        self.document_service = document_service
        self.vault_service = vault_service
        self.vault_context = vault_context

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
        @_vault_option
        def doc_ingest(path: str, name: str | None, vault_name: str | None) -> None:
            """Ingest the file at PATH into the vault."""
            controller._ingest(path, name, vault_name)

        @doc.command("create")
        @click.argument("name")
        @_vault_option
        def doc_create(name: str, vault_name: str | None) -> None:
            """Create a new document named NAME by typing/pasting its text.

            Opens your editor ($VISUAL, then $EDITOR, then the vault's
            configured editor, falling back to vi/nano) on an empty buffer.
            Paste or type the document's contents, save, and close the
            editor to store it as a new document.
            """
            controller._create(name, vault_name)

        @doc.command("list")
        @_vault_option
        def doc_list(vault_name: str | None) -> None:
            """List all documents in the vault."""
            controller._list(vault_name)

        @doc.command("show")
        @click.argument("id", type=int)
        @_vault_option
        def doc_show(id: int, vault_name: str | None) -> None:
            """Show a single document by ID."""
            controller._show(id, vault_name)

        @doc.command("link")
        @click.argument("id", type=int)
        @click.argument("entity_id", type=int)
        @_vault_option
        def doc_link(id: int, entity_id: int, vault_name: str | None) -> None:
            """Link document ID to entity ENTITY_ID."""
            controller._link(id, entity_id, vault_name)

        @doc.command("unlink")
        @click.argument("id", type=int)
        @click.argument("entity_id", type=int)
        @_vault_option
        def doc_unlink(id: int, entity_id: int, vault_name: str | None) -> None:
            """Unlink document ID from entity ENTITY_ID."""
            controller._unlink(id, entity_id, vault_name)

        @doc.command("remove")
        @click.argument("id", type=int)
        @click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt.")
        @_vault_option
        def doc_remove(id: int, yes: bool, vault_name: str | None) -> None:
            """Remove the document with the given ID."""
            controller._remove(id, yes, vault_name)

        return doc

    def _select_vault(self, vault_name: str | None) -> None:
        """
        Point the shared VaultContext at the vault this invocation targets.

        Args:
            vault_name (str | None): An explicit vault name from `--vault`, or
                None to use the default vault.

        Returns:
            None

        Raises:
            VaultError: if the named vault is not registered, or no name was
                given and no default vault is set.
        """
        vault = self.vault_service.resolve_vault(vault_name)
        self.vault_context.set_root(vault.path)

    def _ingest(self, path: str, name: str | None, vault_name: str | None) -> None:
        try:
            self._select_vault(vault_name)
            document = self.document_service.ingest_document(Path(path), name=name)
        except (DocumentError, VaultError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Ingested doc #{document.id}: {document.name}")

    def _create(self, name: str, vault_name: str | None) -> None:
        try:
            self._select_vault(vault_name)
            document = self.document_service.create_document(name)
        except (DocumentError, EditorError, VaultError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Created doc #{document.id}: {document.name}")

    def _list(self, vault_name: str | None) -> None:
        try:
            self._select_vault(vault_name)
            documents = self.document_service.list_documents()
        except (DocumentError, VaultError) as e:
            raise click.ClickException(str(e))

        if not documents:
            click.echo("No documents yet.")
            return

        for d in documents:
            click.echo(f"#{d.id}  {d.name}")

    def _show(self, id: int, vault_name: str | None) -> None:
        try:
            self._select_vault(vault_name)
            document = self.document_service.get_document(id)
            body = self.document_service.get_document_text(id)
            linked = self.document_service.list_linked_entities(id)
        except (DocumentError, VaultError) as e:
            raise click.ClickException(str(e))

        click.echo(f"#{document.id} {document.name}")
        click.echo(f"Source: {document.source_path}")
        click.echo(f"Ingested: {document.ingested_at}")
        click.echo(f"Status: {document.status}")

        if body:
            click.echo("")
            click.echo(body)

        click.echo("")
        if linked:
            click.echo("Mentions:")
            for entity in linked:
                click.echo(f"  entity #{entity.id} [{entity.schema}] {entity.name}")
        else:
            click.echo("Mentions: (none)")

    def _link(self, id: int, entity_id: int, vault_name: str | None) -> None:
        try:
            self._select_vault(vault_name)
            self.document_service.link_document(id, entity_id)
        except (DocumentError, EntityError, VaultError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Linked doc #{id} to entity #{entity_id}")

    def _unlink(self, id: int, entity_id: int, vault_name: str | None) -> None:
        try:
            self._select_vault(vault_name)
            self.document_service.unlink_document(id, entity_id)
        except (DocumentError, EntityError, VaultError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Unlinked doc #{id} from entity #{entity_id}")

    def _remove(self, id: int, yes: bool, vault_name: str | None) -> None:
        try:
            self._select_vault(vault_name)
            document = self.document_service.get_document(id)
        except (DocumentError, VaultError) as e:
            raise click.ClickException(str(e))

        if not yes and not click.confirm(f"Remove doc #{id}: {document.name}?"):
            click.echo("Aborted.")
            return

        try:
            self.document_service.remove_document(id)
        except (DocumentError, VaultError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Removed doc #{id}: {document.name}")

"""Driver layer: CLI entry points. No business logic — call into services only."""

from pathlib import Path

import click

from forte.cli.review_tui import InteractiveReviewer
from forte.db.document_repository import DocumentRepository
from forte.db.mention_repository import MentionRepository
from forte.domain.document_markdown import from_markdown
from forte.services.agent import ProcessResult, process_document
from forte.services.config import Config, ConfigError, load_config, require_api_key
from forte.services.cost import format_cost_summary
from forte.services.discovery import VaultNotFoundError, find_vault_root
from forte.services.document import (
    DocumentError,
    DocumentNotFoundError,
    get_document,
    ingest_document,
    link_document,
    list_documents,
    remove_document,
    unlink_document,
)
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
from forte.services.llm import AnthropicLLMClient, LLMClient
from forte.services.review import AutoApproveReviewer
from forte.services.schema import (
    SchemaError,
    add_schema,
    list_schemas,
    remove_schema,
)
from forte.services.structured import StructuredCallError


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

    mentions = MentionRepository(root).list_for_entity(ent.id)
    click.echo("")
    if mentions:
        click.echo("Mentions:")
        for m in mentions:
            mentioned_doc = DocumentRepository(root).get(m.doc_id)
            doc_name = mentioned_doc.name if mentioned_doc else "(unknown)"
            click.echo(f"  doc #{m.doc_id}: {doc_name}")
    else:
        click.echo("Mentions: (none)")


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


@main.group()
def doc() -> None:
    """Ingest and browse documents in a vault."""


@doc.command("ingest")
@click.argument("path", type=click.Path(exists=False))
@click.option(
    "--name", default=None, help="Human-readable name for the doc (defaults to filename)."
)
def doc_ingest(path: str, name: str | None) -> None:
    """Ingest the file at PATH into the vault."""
    try:
        root = find_vault_root(Path.cwd())
    except VaultNotFoundError as e:
        raise click.ClickException(str(e))

    try:
        document = ingest_document(root, Path(path), name=name)
    except DocumentError as e:
        raise click.ClickException(str(e))

    click.echo(f"Ingested doc #{document.id}: {document.name}")


@doc.command("list")
def doc_list() -> None:
    """List all documents in the vault."""
    try:
        root = find_vault_root(Path.cwd())
    except VaultNotFoundError as e:
        raise click.ClickException(str(e))

    documents = list_documents(root)
    if not documents:
        click.echo("No documents yet.")
        return

    for d in documents:
        click.echo(f"#{d.id}  {d.name}")


@doc.command("show")
@click.argument("id", type=int)
def doc_show(id: int) -> None:
    """Show a single document by ID."""
    try:
        root = find_vault_root(Path.cwd())
    except VaultNotFoundError as e:
        raise click.ClickException(str(e))

    try:
        document = get_document(root, id)
    except DocumentError as e:
        raise click.ClickException(str(e))

    click.echo(f"#{document.id} {document.name}")
    click.echo(f"Source: {document.source_path}")
    click.echo(f"Ingested: {document.ingested_at}")
    click.echo(f"Status: {document.status}")

    if document.processed_path:
        processed_text = (root / document.processed_path).read_text()
        parsed = from_markdown(processed_text)
        click.echo("")
        click.echo(parsed.body)

    mentions = MentionRepository(root).list_for_doc(document.id)
    click.echo("")
    if mentions:
        click.echo("Mentions:")
        for m in mentions:
            try:
                entity_name = get_entity(root, m.entity_id).name
            except EntityError:
                entity_name = "(unknown)"
            click.echo(f"  entity #{m.entity_id}: {entity_name}")
    else:
        click.echo("Mentions: (none)")


@doc.command("link")
@click.argument("id", type=int)
@click.argument("entity_id", type=int)
def doc_link(id: int, entity_id: int) -> None:
    """Link document ID to entity ENTITY_ID."""
    try:
        root = find_vault_root(Path.cwd())
    except VaultNotFoundError as e:
        raise click.ClickException(str(e))

    try:
        link_document(root, id, entity_id)
    except DocumentError as e:
        raise click.ClickException(str(e))

    click.echo(f"Linked doc #{id} to entity #{entity_id}")


@doc.command("unlink")
@click.argument("id", type=int)
@click.argument("entity_id", type=int)
def doc_unlink(id: int, entity_id: int) -> None:
    """Unlink document ID from entity ENTITY_ID."""
    try:
        root = find_vault_root(Path.cwd())
    except VaultNotFoundError as e:
        raise click.ClickException(str(e))

    try:
        unlink_document(root, id, entity_id)
    except DocumentError as e:
        raise click.ClickException(str(e))

    click.echo(f"Unlinked doc #{id} from entity #{entity_id}")


@doc.command("remove")
@click.argument("id", type=int)
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt.")
def doc_remove(id: int, yes: bool) -> None:
    """Remove the document with the given ID."""
    try:
        root = find_vault_root(Path.cwd())
    except VaultNotFoundError as e:
        raise click.ClickException(str(e))

    try:
        document = get_document(root, id)
    except DocumentNotFoundError as e:
        raise click.ClickException(str(e))

    if not yes and not click.confirm(f"Remove doc #{id}: {document.name}?"):
        click.echo("Aborted.")
        return

    try:
        remove_document(root, id)
    except DocumentNotFoundError as e:
        raise click.ClickException(str(e))

    click.echo(f"Removed doc #{id}: {document.name}")


def _build_llm_client(config: Config) -> LLMClient:
    """Construct the real LLM client from vault config.

    This is a construction seam: tests monkeypatch this function to return a
    :class:`~forte.services.llm.StubLLMClient` so the whole test suite stays
    deterministic and free. Production code always gets a real
    :class:`~forte.services.llm.AnthropicLLMClient` here.
    """
    return AnthropicLLMClient(model=config.extraction_model, api_key=require_api_key(config))


def _run_agent_process(root: Path, doc_id: int, *, yes: bool, dry_run: bool) -> None:
    """Shared process-and-render logic for `agent process` and `agent ingest`."""
    try:
        config = load_config(root)
        llm = _build_llm_client(config)
    except ConfigError as e:
        raise click.ClickException(str(e))

    reviewer = AutoApproveReviewer() if yes else InteractiveReviewer()

    try:
        result = process_document(root, doc_id, llm=llm, reviewer=reviewer, dry_run=dry_run)
    except (DocumentNotFoundError, DocumentError) as e:
        raise click.ClickException(str(e))
    except StructuredCallError as e:
        raise click.ClickException(f"Agent run failed: {e}. Nothing was committed.")

    _render_process_result(config, result)


def _render_process_result(config: Config, result: ProcessResult) -> None:
    if not result.approved_changes:
        click.echo("Nothing to do: no proposals were generated for this document.")
        click.echo(format_cost_summary(config.extraction_model, result.usage))
        return

    if result.dry_run:
        click.echo(f"Dry run: {len(result.approved_changes)} change(s) would be committed:")
        for change in result.approved_changes:
            click.echo(f"  - {change}")
        click.echo("Nothing was written.")
    else:
        report = result.commit_report
        assert report is not None
        click.echo(
            f"Committed {len(report.successes)} change(s), "
            f"{len(report.failures)} failure(s)."
        )
        for failure in report.failures:
            click.echo(f"  FAILED: {failure.change} -- {failure.error}")

    click.echo(format_cost_summary(config.extraction_model, result.usage))


@main.group()
def agent() -> None:
    """Run the LLM agent pipeline over documents."""


@agent.command("process")
@click.argument("doc_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="Auto-approve all proposed changes.")
@click.option("--dry-run", is_flag=True, help="Propose changes but write nothing.")
def agent_process(doc_id: int, yes: bool, dry_run: bool) -> None:
    """Run the extract/link/field-extract pipeline against document DOC_ID."""
    try:
        root = find_vault_root(Path.cwd())
    except VaultNotFoundError as e:
        raise click.ClickException(str(e))

    _run_agent_process(root, doc_id, yes=yes, dry_run=dry_run)


@agent.command("ingest")
@click.argument("path", type=click.Path(exists=False))
@click.option("--yes", "-y", is_flag=True, help="Auto-approve all proposed changes.")
@click.option("--dry-run", is_flag=True, help="Propose changes but write nothing.")
def agent_ingest(path: str, yes: bool, dry_run: bool) -> None:
    """Ingest the file at PATH, then run the agent pipeline against it."""
    try:
        root = find_vault_root(Path.cwd())
    except VaultNotFoundError as e:
        raise click.ClickException(str(e))

    try:
        document = ingest_document(root, Path(path))
    except DocumentError as e:
        raise click.ClickException(str(e))

    click.echo(f"Ingested doc #{document.id}: {document.name}")

    _run_agent_process(root, document.id, yes=yes, dry_run=dry_run)

"""Composition root: wires clients, services, and controllers, and exposes
the top-level Click CLI.
"""

import click

from forte.client.fs_document_searcher import FsDocumentSearcher
from forte.client.fs_vault_fs import LocalVaultFs
from forte.client.sqlite_document_db import SqliteDocumentDb
from forte.client.sqlite_entity_db import SqliteEntityDb
from forte.client.sqlite_mention_db import SqliteMentionDb
from forte.client.sqlite_schema_db import SqliteSchemaDb
from forte.client.terminal_editor import TerminalEditorSession
from forte.client.yaml_config_store import YamlConfigStore
from forte.client.yaml_vault_registry import YamlVaultRegistry
from forte.controller.cli_agent_controller import CliAgentController
from forte.controller.cli_document_controller import CliDocumentController
from forte.controller.cli_entity_controller import CliEntityController
from forte.controller.cli_schema_controller import CliSchemaController
from forte.controller.cli_vault_controller import CliVaultController
from forte.model.vault import VaultContext
from forte.service.agent_service import AgentService
from forte.service.config_service import ConfigService
from forte.service.document_service import DocumentService
from forte.service.entity_service import EntityService
from forte.service.schema_service import SchemaService
from forte.service.vault_service import VaultService


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Forte CLI."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# Shared across all clients that need to resolve a vault root. The schema /
# entity / doc controllers set it once per invocation, from the vault named
# by `--vault` or from the registered default vault.
vault_context = VaultContext()

# Add the 'vault' sub-commands
vault_registry = YamlVaultRegistry()
vault_fs = LocalVaultFs()
vault_service = VaultService(vault_registry, vault_fs)
vault_controller = CliVaultController(vault_service)
main.add_command(vault_controller.group())

# Add the 'schema' sub-commands
schema_db = SqliteSchemaDb(vault_context)
schema_service = SchemaService(schema_db)
schema_controller = CliSchemaController(schema_service, vault_service, vault_context)
main.add_command(schema_controller.group())

# Add the 'entity' sub-commands
#
# `document_db` and `mention_db` are constructed here (ahead of their own
# 'doc' sub-commands section below) because EntityService needs them to
# resolve `list_mentioning_documents`.
entity_db = SqliteEntityDb(vault_context)
document_db = SqliteDocumentDb(vault_context)
mention_db = SqliteMentionDb(vault_context)
entity_service = EntityService(entity_db, schema_db, mention_db, document_db)
entity_controller = CliEntityController(entity_service, vault_service, vault_context)
main.add_command(entity_controller.group())

# Add the 'doc' sub-commands
#
# `config_service` and `editor` are constructed here (ahead of the 'agent'
# sub-commands below) because DocumentService needs the editor to power
# `create_document`.
config_service = ConfigService(YamlConfigStore(vault_context))
editor = TerminalEditorSession(config_service)
document_searcher = FsDocumentSearcher(vault_context)
document_service = DocumentService(document_db, mention_db, entity_db, editor, document_searcher)
document_controller = CliDocumentController(document_service, vault_service, vault_context)
main.add_command(document_controller.group())

# Add the 'agent' sub-commands.
#
# The LLM client is deliberately NOT built here: constructing it needs an API
# key and a selected vault, and neither exists at wiring time. CliAgentController
# builds it lazily per invocation (its `_build_llm_client` seam) and installs it
# on the AgentService just before a run, so a vault-less or key-less invocation
# fails with a clean message instead of at import.
agent_service = AgentService(
    None,  # type: ignore[arg-type]  # installed per-invocation by CliAgentController
    config_service,
    document_service,
    entity_service,
    schema_service,
)
agent_controller = CliAgentController(
    agent_service, document_service, config_service, vault_service, vault_context, editor
)
main.add_command(agent_controller.group())


if __name__ == "__main__":
    main()

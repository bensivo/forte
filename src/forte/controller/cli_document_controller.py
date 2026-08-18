import sys
from pathlib import Path

import click

from forte.model.document import DocumentError, DocumentMatch
from forte.model.editor import EditorError
from forte.model.entity import Entity, EntityError
from forte.model.entity_picker import EntityPickerAbortedError, EntityPickerError
from forte.model.vault import VaultContext, VaultError
from forte.service.document_service import DocumentService
from forte.service.vault_service import VaultService

# Long matching lines (e.g. a one-line PDF extract) are truncated around the
# first match so a single result can't flood the terminal.
_MAX_MATCH_LINE_LENGTH = 200


# Adds the shared `--vault <name>` selector to a doc subcommand. Defined once
# so every subcommand spells the option identically.
def _vault_option(f):
    return click.option(
        "--vault",
        "vault_name",
        default=None,
        help="Name of the vault to operate on (defaults to the default vault).",
    )(f)


def _truncate_match_line(
    line: str, spans: list[tuple[int, int]], max_length: int = _MAX_MATCH_LINE_LENGTH
) -> tuple[str, list[tuple[int, int]]]:
    """
    Truncate a match line to ``max_length`` characters, windowed around the
    first match span, shifting any spans to their new offsets.

    Args:
        line (str): The full matching line.
        spans (list[tuple[int, int]]): Match spans as (start, end) character
            offsets within ``line``.
        max_length (int): The maximum length of the returned line, not
            counting ellipses added for truncation.

    Returns:
        (tuple[str, list[tuple[int, int]]]) The (possibly truncated) line,
            and its spans adjusted to offsets within that line. Spans that
            fall entirely outside the truncated window are dropped.
    """
    if len(line) <= max_length:
        return line, spans

    if not spans:
        return line[:max_length] + "...", []

    first_start, _ = spans[0]
    half = max_length // 2
    start = max(0, first_start - half)
    end = min(len(line), start + max_length)
    start = max(0, end - max_length)

    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(line) else ""
    windowed = line[start:end]
    new_line = prefix + windowed + suffix

    shift = len(prefix) - start
    window_lo, window_hi = len(prefix), len(prefix) + len(windowed)
    new_spans: list[tuple[int, int]] = []
    for s, e in spans:
        ns, ne = max(s + shift, window_lo), min(e + shift, window_hi)
        if ns < ne:
            new_spans.append((ns, ne))

    return new_line, new_spans


def _highlight_spans(line: str, spans: list[tuple[int, int]]) -> str:
    """
    Bold each matched span within ``line`` via `click.style`.

    Args:
        line (str): The line to highlight.
        spans (list[tuple[int, int]]): Match spans as (start, end) character
            offsets within ``line``, in ascending order.

    Returns:
        (str) ``line`` with each span wrapped in `click.style(bold=True)`.
            Click strips styling automatically when stdout isn't a TTY.
    """
    if not spans:
        return line

    parts = []
    cursor = 0
    for start, end in spans:
        if start > cursor:
            parts.append(line[cursor:start])
        parts.append(click.style(line[start:end], bold=True))
        cursor = end
    parts.append(line[cursor:])
    return "".join(parts)


def _render_match(match: DocumentMatch, line_number_width: int) -> str:
    """
    Render one matching line for display, right-aligning the line number and
    highlighting/truncating the match text.

    Args:
        match (DocumentMatch): The match to render.
        line_number_width (int): The width to right-align the line number to,
            so line numbers within a document group line up.

    Returns:
        (str) A single indented, formatted line ready for `click.echo`.
    """
    line, spans = _truncate_match_line(match.line, match.spans)
    rendered_line = _highlight_spans(line, spans)
    line_number = click.style(f"line {match.line_number:>{line_number_width}}", dim=True)
    return f"  {line_number}: {rendered_line}"


class CliDocumentController:
    """
    CLI interface for DocumentService. Wires DocumentService operations up as
    a `doc` Click command group
    (ingest/create/list/show/search/link/link-interactive/unlink/remove),
    translating DocumentError, EntityError, EntityPickerError, and
    VaultError into Click errors.
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
        @click.option(
            "--no-link",
            "no_link",
            is_flag=True,
            default=False,
            help="Skip the interactive entity-linking step that runs after ingest.",
        )
        @_vault_option
        def doc_ingest(
            path: str, name: str | None, no_link: bool, vault_name: str | None
        ) -> None:
            """Ingest the file at PATH into the vault.

            Once the document is stored (or, for a re-ingested/deduped file,
            once the existing document is found), offers the same
            interactive entity-linking prompt as `forte doc link-interactive`.
            Pass --no-link to skip that second step; it is also skipped
            automatically when stdin is not an interactive terminal.
            """
            controller._ingest(path, name, no_link, vault_name)

        @doc.command("create")
        @click.argument("name")
        @click.option(
            "--no-link",
            "no_link",
            is_flag=True,
            default=False,
            help="Skip the interactive entity-linking step that runs after saving.",
        )
        @_vault_option
        def doc_create(name: str, no_link: bool, vault_name: str | None) -> None:
            """Create a new document named NAME by typing/pasting its text.

            Opens your editor ($VISUAL, then $EDITOR, then the vault's
            configured editor, falling back to vi/nano) on an empty buffer.
            Paste or type the document's contents, save, and close the
            editor to store it as a new document.

            Once the document is stored, offers the same interactive
            entity-linking prompt as `forte doc link-interactive`. Pass
            --no-link to skip that second step; it is also skipped
            automatically when stdin is not an interactive terminal.
            """
            controller._create(name, no_link, vault_name)

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

        @doc.command("link-interactive")
        @click.argument("id", type=int)
        @_vault_option
        def doc_link_interactive(id: int, vault_name: str | None) -> None:
            """Interactively link document ID to one or more entities.

            Type a few characters of an entity's name (matched literally,
            case-insensitively, against names and aliases) to search, then
            press Enter to add the highlighted suggestion to the running
            list of links. Submit an empty line (or Ctrl-D) to finish the
            session. Ctrl-C aborts the session, keeping whatever was
            already linked before the interrupt.
            """
            controller._link_interactive(id, vault_name)

        @doc.command("unlink")
        @click.argument("id", type=int)
        @click.argument("entity_id", type=int)
        @_vault_option
        def doc_unlink(id: int, entity_id: int, vault_name: str | None) -> None:
            """Unlink document ID from entity ENTITY_ID."""
            controller._unlink(id, entity_id, vault_name)

        @doc.command("search")
        @click.argument("query")
        @click.option(
            "--case-sensitive",
            "-s",
            is_flag=True,
            default=False,
            help="Match case-sensitively (default: case-insensitive).",
        )
        @click.option(
            "--regex",
            "-r",
            is_flag=True,
            default=False,
            help="Treat QUERY as a regular expression instead of literal text.",
        )
        @click.option(
            "--limit",
            "-n",
            "limit",
            type=int,
            default=None,
            help="Maximum number of matches to show per document.",
        )
        @_vault_option
        def doc_search(
            query: str,
            case_sensitive: bool,
            regex: bool,
            limit: int | None,
            vault_name: str | None,
        ) -> None:
            """Search document bodies for QUERY.

            QUERY is matched literally (case-insensitively) by default, like
            a normal text-editor search. Pass --regex to treat QUERY as a
            regular expression instead, and --case-sensitive to disable
            case-insensitive matching.
            """
            controller._search(query, case_sensitive, regex, limit, vault_name)

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

    def _ingest(self, path: str, name: str | None, no_link: bool, vault_name: str | None) -> None:
        try:
            self._select_vault(vault_name)
            document = self.document_service.ingest_document(Path(path), name=name)
        except (DocumentError, VaultError, EntityPickerError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Ingested doc #{document.id}: {document.name}")
        self._offer_link_step(document, no_link)

    def _create(self, name: str, no_link: bool, vault_name: str | None) -> None:
        try:
            self._select_vault(vault_name)
            document = self.document_service.create_document(name)
        except (DocumentError, EditorError, VaultError, EntityPickerError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Created doc #{document.id}: {document.name}")
        self._offer_link_step(document, no_link)

    def _offer_link_step(self, document, no_link: bool) -> None:
        """
        Run the shared follow-on interactive link step for `create`/`ingest`,
        once the document already exists (persist first, link second): does
        nothing if ``no_link`` is set, otherwise delegates to
        `_run_interactive_link` (skipping rather than failing on a non-TTY
        stdin) and reports the outcome the same way `link-interactive` does.

        Args:
            document: The just-created/ingested document (has `.id`, `.name`).
            no_link (bool): Whether `--no-link` was passed.

        Returns:
            None

        Raises:
            click.ClickException: on abort (after reporting partial progress
                and a resume hint) or on a propagated service/picker error.
        """
        if no_link:
            return

        try:
            linked = self._run_interactive_link(document.id, fail_on_non_tty=False)
        except EntityPickerAbortedError:
            self._echo_link_abort(document.id, suggest_resume=True)
        except (DocumentError, EntityError, EntityPickerError, VaultError) as e:
            raise click.ClickException(str(e))

        if linked is None:
            return

        self._echo_link_summary(document, linked)

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

    def _search(
        self,
        query: str,
        case_sensitive: bool,
        regex: bool,
        limit: int | None,
        vault_name: str | None,
    ) -> None:
        try:
            self._select_vault(vault_name)
            results = self.document_service.search_documents(
                query,
                case_sensitive=case_sensitive,
                regex=regex,
                limit_per_document=limit,
            )
        except (DocumentError, VaultError) as e:
            raise click.ClickException(str(e))

        if not results:
            click.echo("No matches.")
            return

        total_matches = 0
        for i, result in enumerate(results):
            if i > 0:
                click.echo("")
            click.echo(f"doc #{result.document.id}: {result.document.name}")

            width = max(len(str(m.line_number)) for m in result.matches)
            for match in result.matches:
                click.echo(_render_match(match, width))
            total_matches += len(result.matches)

        doc_word = "document" if len(results) == 1 else "documents"
        match_word = "match" if total_matches == 1 else "matches"
        click.echo("")
        click.echo(f"{len(results)} {doc_word}, {total_matches} {match_word}")

    def _link(self, id: int, entity_id: int, vault_name: str | None) -> None:
        try:
            self._select_vault(vault_name)
            self.document_service.link_document(id, entity_id)
        except (DocumentError, EntityError, VaultError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Linked doc #{id} to entity #{entity_id}")

    def _run_interactive_link(
        self, document_id: int, *, fail_on_non_tty: bool = True
    ) -> list[Entity] | None:
        """
        Guard and invoke the interactive entity-linking flow for
        ``document_id``, against the vault already pointed at by
        ``self.vault_context``.

        Shared by `link-interactive`, `create`, and `ingest`, so the guards
        below can never drift apart between the three entry points:
          - stdin must be a TTY. When ``fail_on_non_tty`` is True (the
            standalone `link-interactive` command), a non-interactive
            invocation fails fast with a message pointing at the
            non-interactive `forte doc link <doc_id> <entity_id>`
            alternative, instead of hanging or crashing inside
            prompt-toolkit. When False (the `create`/`ingest` follow-on
            step), a non-interactive invocation is silently skippable
            instead: a short note is printed and `None` is returned, so
            scripts and agents piping input never land in a prompt.
          - the vault must have at least one entity to offer; otherwise a
            short note is printed and the picker is never invoked (no
            empty completion menu).
        Everything else -- document-existence validation, the actual
        picker session, and linking each selection -- is delegated to
        `DocumentService.link_document_interactive`. Callers are
        responsible for translating the exceptions it can raise (including
        `EntityPickerAbortedError`) into user-facing output.

        Args:
            document_id (int): The id of the document to link entities to.
            fail_on_non_tty (bool): Whether a non-TTY stdin should raise
                (the standalone command) or be skipped quietly (the
                `create`/`ingest` follow-on step).

        Returns:
            (list[Entity] | None) The entities newly linked, in selection
                order. `None` if the step was skipped -- because the vault
                has no entities to offer, or (when ``fail_on_non_tty`` is
                False) stdin isn't a TTY -- in either case a short message
                has already been printed, so the caller should treat it as
                a completed, zero-link run rather than print its own
                summary.

        Raises:
            click.ClickException: if stdin is not a TTY and
                ``fail_on_non_tty`` is True.
            DocumentError: propagated from
                `DocumentService.link_document_interactive` (e.g. an
                unknown document id).
            EntityPickerAbortedError: propagated if the picker session is
                aborted by the user.
        """
        if not sys.stdin.isatty():
            if not fail_on_non_tty:
                click.echo("Skipping the link step: stdin is not interactive.")
                return None
            raise click.ClickException(
                "link-interactive requires an interactive terminal. "
                "Use `forte doc link <doc_id> <entity_id>` instead."
            )

        if not self.document_service.search_entities(""):
            click.echo("No entities to link.")
            return None

        click.echo("")
        click.echo("Link entities (type to search, Enter to add, empty line to finish):")
        return self.document_service.link_document_interactive(document_id)

    def _echo_link_summary(self, document, linked: list[Entity]) -> None:
        """Print the shared "N entities linked to doc #X: name" summary
        (or the "none linked" note) used by `link-interactive`, `create`,
        and `ingest` alike."""
        if linked:
            word = "entity" if len(linked) == 1 else "entities"
            click.echo(f"Linked {len(linked)} {word} to doc #{document.id}: {document.name}")
            for entity in linked:
                click.echo(f"  #{entity.id} [{entity.schema}] {entity.name}")
        else:
            click.echo(f"No entities linked to doc #{document.id}: {document.name}")

    def _echo_link_abort(self, document_id: int, *, suggest_resume: bool) -> None:
        """Print the shared abort message reporting whatever was linked
        before an `EntityPickerAbortedError`, then raise the
        `click.ClickException` that gives the process its non-zero exit.

        Args:
            document_id (int): The document the aborted session targeted.
            suggest_resume (bool): Whether to add a
                `forte doc link-interactive <id>` resume hint -- used by
                `create`/`ingest`, where the user hasn't already run that
                command, but not by `link-interactive` itself.

        Raises:
            click.ClickException: always, to end the command with a
                non-zero exit code.
        """
        linked_so_far = self.document_service.list_linked_entities(document_id)
        if linked_so_far:
            word = "entity" if len(linked_so_far) == 1 else "entities"
            click.echo(f"Aborted. Linked {len(linked_so_far)} {word} before the abort:")
            for entity in linked_so_far:
                click.echo(f"  #{entity.id} [{entity.schema}] {entity.name}")
        else:
            click.echo("Aborted. No entities were linked.")
        if suggest_resume:
            click.echo(f"Resume with `forte doc link-interactive {document_id}`.")
        raise click.ClickException("Entity linking session aborted.")

    def _link_interactive(self, id: int, vault_name: str | None) -> None:
        try:
            self._select_vault(vault_name)
            document = self.document_service.get_document(id)
        except (DocumentError, VaultError) as e:
            raise click.ClickException(str(e))

        click.echo(f"doc #{document.id}: {document.name}")

        try:
            linked = self._run_interactive_link(id)
        except EntityPickerAbortedError:
            self._echo_link_abort(id, suggest_resume=False)
        except (DocumentError, EntityError, EntityPickerError, VaultError) as e:
            raise click.ClickException(str(e))

        if linked is None:
            return

        self._echo_link_summary(document, linked)

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

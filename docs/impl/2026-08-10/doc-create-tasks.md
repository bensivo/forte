# `forte doc create` — Task Breakdown

Feature: remove the "find the file on disk first" friction (step 5 of
[docs/input/2026-08-10 friction-points.md](../../input/2026-08-10%20friction-points.md)) by letting a user
paste document content straight into the vault. `forte doc create <name>` opens the same terminal editor
used by `forte agent ingest --interactive`, the user pastes (or types) the content, saves, and closes —
Forte stores the result as a normal document with no source file involved.

Tasks:
- Move the terminal editor to the client layer, behind an `IEditor` interface
- Add a text-sourced write path to `IDocumentDb`
- Implement `add_text` in `SqliteDocumentDb`
- Add `DocumentService.create_document`
- Add the `forte doc create` CLI command and wiring
- Add e2e tests for `forte doc create`

---

Task: Move the terminal editor to the client layer, behind an `IEditor` interface
ACs:
- `interface/editor.py` defines `IEditor` with a single `edit(text: str) -> str` method: present `text` for
  editing, return the edited contents. Storage/IO description only, no `Raises:` section, no business logic.
- `client/terminal_editor.py` holds `TerminalEditorSession` (implementing `IEditor`) and
  `resolve_editor_command`; nothing about it imports from the agent feature.
- The abort error raised when the editor exits non-zero lives in a feature-neutral `model/editor.py`
  (`EditorError` base plus `EditorAbortedError`).
- `forte agent ingest --interactive` and the bulk-commit flow keep working exactly as before —
  `forte.model.agent.EditorAbortedError` still resolves to the same exception class (re-export or alias),
  so existing agent `except` clauses are unchanged.
- The old `controller/terminal_editor.py` and the `EditorSession` protocol in `service/agent/_editor.py`
  are gone, with their call sites updated to `IEditor`.
- One `TerminalEditorSession` is constructed in `main.py` and injected wherever it's needed, rather than
  each controller building its own.
Implementation Notes:
- Rationale for the move: the editor doesn't trigger behavior, it's *called by* services. It's a
  low-level operation against an external dependency that happens to be `vim`/`code --wait` — a client, not
  a controller. Putting it behind `IEditor` is also what makes services trivially unit-testable with a
  scripted `edit` stub.
- Today: `src/forte/controller/terminal_editor.py` raises `forte.model.agent.EditorAbortedError`, and the
  `EditorSession` protocol lives in `src/forte/service/agent/_editor.py`. Both are being replaced by the
  `interface/` + `client/` + `model/` split above.
- Naming per the style guide is `<technology><Interface>` → strictly `TerminalEditor` for `IEditor`. Keep
  the existing `TerminalEditorSession` name if you'd rather not churn the agent call sites; either is fine,
  just be consistent.
- Update `terminal_editor.py`'s module docstring: the long explanation of why it lives in `controller/` is
  now wrong and should be replaced with the client-layer rationale above.
- `model/editor.py` follows the exception convention: base docstring is just
  `"""Base class for editor errors."""`, subclass docstring names the one condition that raises it.
- `CliAgentController._build_editor_session` can go away once `main.py` owns the instance — the editor
  resolution inside `edit()` is already lazy, so there's no wiring-time vault or config dependency to
  work around. Keep `process_document_bulk`'s `editor` call parameter as-is to limit blast radius;
  it just gets handed the wired client instead of a controller-built one.

Task: Add a text-sourced write path to `IDocumentDb`
ACs:
- `IDocumentDb` exposes a method for persisting a document whose content came from memory rather than a
  file on disk, e.g. `add_text(name: str, content_hash: str, text: str) -> Document`.
- The docstring describes it as storage/IO only — no validation, no `Raises:` section.
- The method sits in the interface in the conventional order (alongside `add`, before `list`).
Implementation Notes:
- See `src/forte/interface/document_db.py`. The existing `add(source_path, content_hash, extracted_text, name)`
  is file-oriented: it copies bytes from `source_path` into `docs/raw/`. A pasted doc has no source file,
  so overloading `add` with a nullable path would push branching into every implementation — a second
  method is cleaner.
- Style guide: interface method docstrings describe storage operations only; validation and error-raising
  belong to the service that calls them.

Task: Implement `add_text` in `SqliteDocumentDb`
ACs:
- `add_text` writes a raw copy under `docs/raw/` containing exactly the text the user supplied, writes the
  processed markdown copy under `docs/processed/<id>.md` with the usual frontmatter, and inserts the
  `documents` row — matching what `add` produces for a file ingest.
- The raw filename is derived from the document name (slugified, `.md` suffix) and collides safely with
  existing files via the same numeric-suffix disambiguation `add` uses.
- `source_path` on the stored row records that the document was created in-place rather than ingested from
  a path (e.g. the literal `(created)`), and `status` matches what `add` sets.
- `doc list`, `doc show`, `doc remove`, and `doc link`/`unlink` all work against the resulting row with no
  further changes.
Implementation Notes:
- See `src/forte/client/sqlite_document_db.py`. Reuse `_resolve_raw_path`, `_rel_path`, and the
  insert-then-write-processed-then-update-`processed_path` sequence from `add`; factor the shared tail out
  rather than copy-pasting it if that stays readable.
- Raw copy for a pasted doc is the text itself (`write_text(..., encoding="utf-8")`), not a `shutil.copy2`.
- The processed body is the same text — there's no extraction step, since the input is already plain text.
- Slugify defensively: the name is free-form user input and must not escape `docs/raw/` (no path
  separators, no `..`). A `_leading_underscore`, `UPPER_SNAKE_CASE` module-level regex with a one-line
  comment above it is the style-guide-conformant way to express the allowed characters.
- Keep `to_markdown(stored, text)` for the processed copy so frontmatter stays identical in shape to
  ingested docs.

Task: Add `DocumentService.create_document`
ACs:
- `DocumentService` takes an `IEditor` in its constructor, alongside its existing db dependencies.
- `DocumentService.create_document(name: str) -> Document` validates `name`, opens an empty editing
  session via `editor.edit("")`, validates the returned text, persists via `document_db.add_text`, and
  returns the stored `Document` with its assigned id.
- Empty/whitespace-only `name` and an empty/whitespace-only editor result are both rejected with typed
  errors; `name` is checked before the editor is ever opened, and nothing is written to `document_db` in
  either failure case.
- `EditorAbortedError` propagates unchanged (nothing has been written by the time the editor runs).
- New exception subclasses live in `model/document.py` under the existing `DocumentError` base (e.g.
  `InvalidDocumentNameError`, `EmptyDocumentError`), each with a docstring naming the one condition that
  raises it.
- The method's docstring has a `Raises:` section naming every exception type and its condition, including
  the propagated `EditorAbortedError`.
- Unlike `ingest_document`, there is no identity/dedup check: creating two documents with the same name and
  the same content produces two documents.
Implementation Notes:
- See `src/forte/service/document_service.py`. Hash the text bytes with the existing
  `compute_content_hash(text.encode("utf-8"))` so pasted docs carry a hash of the same shape as ingested ones.
- Style guide: validate everything before the first write call — no partial writes needing cleanup.
- No dedup is deliberate: `find_by_identity` keys off a real source path, which pasted docs don't have, and
  a user pasting the same note twice is more likely intentional than accidental. State this in the class or
  method docstring so it doesn't read as an oversight.
- The editor is a constructor dependency (`IEditor`), not a function parameter: it's a dependency of the
  feature, not an input to the call. This is also what makes the service unit-testable — a fake `IEditor`
  returning canned text exercises `create_document` end to end with no subprocess.
- Validation order matters: check `name` first (cheap, and it would be rude to make the user paste a
  document only to then reject the name), then open the editor, then check the returned text.

Task: Add the `forte doc create` CLI command and wiring
ACs:
- `forte doc create <name>` opens the user's editor (same resolution order as `forte agent ingest`:
  `$VISUAL` → `$EDITOR` → `config.editor` → `vi`/`nano`), on an empty temp `.md` buffer.
- On save-and-close, the buffer's contents are stored as a new document and the command prints a message in
  the same shape as ingest, e.g. `Created doc #3: Kickoff Notes`, exiting 0.
- If the editor exits non-zero, nothing is written to the vault and the command fails with a clean
  `ClickException` message, not a traceback.
- If the user saves an empty buffer, nothing is written and the command fails with a clean message.
- The command supports the shared `--vault <name>` option, like every other `doc` subcommand.
- `forte doc --help` lists `create`, and `forte doc create --help` explains the paste-into-editor flow.
Implementation Notes:
- See `src/forte/controller/cli_document_controller.py`. Follow the established shape: a nested
  `@doc.command("create")` callback that only unpacks args and delegates to `controller._create(...)`, with
  all logic, error handling, and echoing in the private method.
- `_create` must call `self._select_vault(vault_name)` before the service call, like every sibling method.
- Wrap the service call in `try/except (DocumentError, EditorError, VaultError)` →
  `click.ClickException(str(e))`, catching the base classes rather than individual subclasses.
- The controller knows nothing about the editor beyond that error type — `_create` is just
  `self._select_vault(vault_name)`, `self.document_service.create_document(name)`, `click.echo(...)`.
- Wiring in `src/forte/main.py`: construct `TerminalEditorSession(config_service)` and pass it into
  `DocumentService`. Note `config_service` is currently constructed *after* `document_service` there, so the
  wiring order needs adjusting; the agent block below it then reuses the same editor instance.
- The service seeds the buffer with an empty string (or a single trailing newline). Don't seed a
  template/comment header: the point is that a paste lands as the literal document body.

Task: Add e2e tests for `forte doc create`
ACs:
- A new `tests/e2e/test_doc_create.py` covers, one test per scenario:
  - creating a doc from pasted editor content exits 0 and prints the new id and name
  - the created doc appears in `forte doc list` and its content comes back from `forte doc show <id>`
  - a raw copy and a processed copy exist in the vault, and the processed copy carries frontmatter plus the
    pasted body verbatim
  - a created doc can be linked to an entity with `forte doc link` and shows up under Mentions
  - an editor that exits non-zero leaves the vault with no new document
  - an editor that saves an empty buffer leaves the vault with no new document
- All tests pass via `pytest tests/e2e/test_doc_create.py`, and the existing e2e suite still passes.
Implementation Notes:
- These tests are the behavior source of truth for the feature — there is no separate spec document. Give
  each test a `# Scenario: <title>` comment above it, as `tests/e2e/test_doc_crud.py` already does, and make
  the scenario list read as the feature's definition rather than as coverage of something written elsewhere.
- Copy the harness conventions from `tests/e2e/test_doc_crud.py`: the `FORTE_BIN` resolution from
  `sys.executable`, the `forte(args, home)` helper, `tmp_path`-scoped fake `HOME`, and the `a_vault(tmp_path)`
  setup helper. Consider lifting the shared helpers into a `conftest.py` only if the duplication actually
  bites — the existing files each keep their own copy.
- The editor is driven by writing a tiny fake-editor script into `tmp_path` and passing `EDITOR=<python> <script>`
  in the subprocess env (the `forte` helper's `env=` dict needs to accept an override). Three variants are
  needed: one that writes fixed content into the file it's handed, one that exits non-zero, and one that
  writes nothing. Use `sys.executable` to invoke the script so it doesn't depend on an ambient `python`.
- Note the editor command string is `shlex.split`, so `EDITOR="/path/to/python /path/to/fake_editor.py"`
  works — no shell wrapper needed. Avoid spaces in the generated paths.
- Use gherkin-style `# Given:` / `# When:` / `# Then:` comments per block, and assert only on things a user
  could observe: exit codes, stdout, and files in the vault directory. No SQLite assertions.

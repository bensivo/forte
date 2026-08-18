# Interactive entity linking — Task Breakdown

Feature: remove the "look up every entity id by hand before you can link" friction (step 6 of
[docs/input/2026-08-10 friction-points.md](../../input/2026-08-10%20friction-points.md)) by adding an
interactive entity-linking prompt: the user types a few characters of an entity name and picks the real
entity from an autocomplete list. Docs link to many entities, so the prompt loops: pick one, it is
appended to a running list, pick the next, submit an empty line to finish.

**This is built as one reusable operation with three entry points**, not as a step inside
`forte doc create`:

1. `forte doc link-interactive <id>` — run the prompt against any existing document, standalone.
2. `forte doc create <name>` — after the editor step, as a second step.
3. `forte doc ingest <path>` — after the file is ingested, as a second step.

All three call the same `DocumentService` operation, which calls the same `IEntityPicker`. The
standalone command is the primary deliverable and the one the other two are defined in terms of — build
it first, and the other entry points are a couple of lines each.

```
$ forte doc link-interactive 12
doc #12: Acme Kickoff Notes

Link entities (type to search, Enter to add, empty line to finish):
> ali
  #1 [person] Alice
  #7 [person] Alice Nguyen
  #3 [client] Alignment Health
> #1 [person] Alice
Linked: #1 [person] Alice
> acme
  #4 [client] Acme Corp
> #4 [client] Acme Corp
Linked: #4 [client] Acme Corp
>
Linked 2 entities to doc #12: Acme Kickoff Notes
```

`forte doc create` and `forte doc ingest` show the same prompt as a second step once the document is
stored, and both take `--no-link` to skip it.

The autocomplete is powered by [prompt-toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit),
which is the first interactive-prompt dependency in the project (the solution design's "Rich prompts"
choice covers confirm/ask flows; nothing in Rich does completion-as-you-type). Matching is literal
substring matching over entity names and aliases — no LLM, no embeddings, no network calls. This is
independent of the deferred semantic `entity search`.

Tasks:
- Add `prompt-toolkit` as a dependency
- Add `EntityService.search_entities` for substring entity lookup
- Define the `IEntityPicker` interface and its error model
- Implement `PromptToolkitEntityPicker`
- Add `DocumentService.link_document_interactive`
- Add the `forte doc link-interactive` CLI command and wiring
- Offer the link step from `forte doc create` and `forte doc ingest`
- Write the spec scenarios for interactive linking
- Add e2e tests for interactive linking

---

Task: Add `prompt-toolkit` as a dependency
ACs:
- `prompt-toolkit` is listed in `[project].dependencies` in `pyproject.toml`, with a lower bound of
  `>=3.0` (the 3.x API — `PromptSession`, `Completer`, `Completion` — is what the rest of these tasks
  assume).
- `uv.lock` is regenerated and committed so a fresh `uv sync` installs it.
- `uv run forte --help` still works, and the existing test suite still passes.
Implementation Notes:
- prompt-toolkit is pure python with no compiled extensions and no transitive deps beyond `wcwidth`, so
  it does not narrow forte's install matrix — unlike the ripgrep packages rejected in
  [the doc-search breakdown](../2026-08-11/doc-search-tasks.md).
- It is already an indirect dependency in many environments (ipython, click's own ecosystem), but do not
  rely on that: declare it explicitly.
- Nothing outside `src/forte/client/` may import prompt-toolkit. That is the whole point of the
  `IEntityPicker` interface below, and it is what keeps services unit-testable without a terminal.

Task: Add `EntityService.search_entities` for substring entity lookup
ACs:
- `EntityService.search_entities(query: str, *, limit: int | None = None) -> list[Entity]` returns the
  entities whose **name or any alias** contains `query` as a case-insensitive substring, across all
  schemas.
- The query is normalized the same way `_normalize` already normalizes names (lowercase, collapse
  internal whitespace, strip) before matching, so `"  ali "` and `"ali"` behave identically.
- An empty or whitespace-only query returns the first `limit` entities (or all of them) rather than
  raising — that is what backs the "show me everything before I've typed anything" state of the prompt.
- Results are ranked deterministically: name matches before alias-only matches, prefix matches before
  mid-string matches, then ascending entity id as the tiebreak. Same inputs always produce the same
  order.
- Each entity appears at most once, even when it matches on both its name and an alias.
- `limit`, when given, caps the number of results returned (applied after ranking).
- Unit tested with a fake `IEntityDb`: name match, alias match, case-insensitivity, ranking order,
  de-duplication, empty query, and `limit`.
Implementation Notes:
- See `src/forte/service/entity_service.py`. The existing module-level `find_candidates` is a *different*
  function with a *different* job: it is schema-scoped exact/normalized matching used by the extraction
  pipeline to decide "is this the same thing?". Do not extend it or reuse it here — substring search is
  intentionally fuzzier and intentionally cross-schema (a user typing "ali" doesn't know or care whether
  Alice is a `person` or a `contact`). Reuse `_normalize`; leave `find_candidates` alone.
- Implement as a method on `EntityService` (it needs `entity_db.list()`), not a module-level pure
  function, but keep the matching/ranking logic in a small pure helper next to `_normalize` if that makes
  it easier to unit test.
- No new `IEntityDb` method: `entity_db.list()` already returns everything, and vaults are small enough
  that filtering in python is correct here. If a vault ever gets big enough for this to matter, the fix is
  a SQL `LIKE` query behind the existing interface, not a change to this signature.
- Rank prefix-over-substring because that is what makes typing `"ali"` put `Alice` above
  `Natalie` — the single most visible quality signal in the prompt.

Task: Define the `IEntityPicker` interface and its error model
ACs:
- `interface/entity_picker.py` defines `IEntityPicker` with a single method, e.g.
  `pick(search: Callable[[str], list[Entity]]) -> list[Entity]`: run an interactive selection session,
  calling `search` to resolve what the user has typed so far, and return the entities the user chose,
  in selection order.
- The docstring describes an interaction/IO operation only: no validation, no business logic, no
  `Raises:` section for feature errors (mirroring `interface/editor.py`).
- Returning an empty list is a valid, non-error outcome: the user chose to link nothing.
- `model/entity_picker.py` defines `EntityPickerError` (base, docstring is just
  `"""Base class for entity picker errors."""`) plus `EntityPickerAbortedError`, whose docstring names
  the one condition that raises it (the user aborted the selection session, e.g. Ctrl-C).
Implementation Notes:
- Style guide: interfaces are `I<Noun>`, describe IO only, and their methods don't raise feature errors.
  `src/forte/interface/editor.py` is the closest analogue — `IEditor.edit(text) -> str` is exactly this
  shape, one method, human in the middle.
- Taking a `search` **callback** rather than a `list[Entity]` is the key design decision. It keeps the
  ranking logic in `EntityService` (unit-testable, no terminal) while keeping the keystroke loop in the
  client (no service dependency on prompt-toolkit), and it means the picker never needs an
  `IEntityDb` of its own. The service binds `self.entity_service.search_entities` — or a small lambda —
  and hands it over.
- The picker deals in `Entity` objects, not ids: the caller already has the full records it needs for
  display and for linking, and round-tripping through ids would just invite a second lookup.
- `model/entity_picker.py` is feature-neutral in the same way `model/editor.py` is — the picker is a
  human-interaction primitive, not part of the entity feature's business rules.

Task: Implement `PromptToolkitEntityPicker`
ACs:
- `client/prompt_toolkit_entity_picker.py` defines `PromptToolkitEntityPicker(IEntityPicker)`, the only
  module in the codebase that imports `prompt_toolkit`.
- `pick` runs a loop over a single `PromptSession`: each iteration shows a prompt, offers completions
  from `search(<current input>)` as the user types, and appends the chosen entity to the result list.
- Completions are displayed as `#<id> [<schema>] <name>` — e.g. `#1 [person] Alice` — so the user sees
  the id, type, and name for every candidate. The completion menu updates on every keystroke.
- Submitting an empty line ends the loop and returns everything picked so far.
- Selecting an entity that was already picked is a no-op with a brief message rather than a duplicate
  entry in the returned list.
- Submitting text that matches no entity re-prompts with a short "no match" message instead of returning
  or crashing; the previously picked entities are preserved.
- Ctrl-C (`KeyboardInterrupt`) raises `EntityPickerAbortedError`. Ctrl-D (`EOFError`) ends the loop
  normally, like an empty line — it is the standard "I'm done" key.
- Already-picked entities are shown back to the user as a running list (or at least confirmed one line at
  a time as each is added) so the user can see what they've accumulated.
- Unit tested without a real terminal: drive the session with prompt-toolkit's pipe input and a dummy
  output, feeding scripted keystrokes. Cover: pick one, pick several, empty line to finish immediately,
  no-match re-prompt, duplicate selection, and Ctrl-C → `EntityPickerAbortedError`.
Implementation Notes:
- Style guide names clients `<technology><Interface>`; `PromptToolkitEntityPicker` is the literal
  application of that to `IEntityPicker`.
- Suggested shape: a `Completer` subclass whose `get_completions(document, complete_event)` calls
  `search(document.text_before_cursor)` and yields
  `Completion(text=<the display string>, start_position=-len(document.text_before_cursor), display=<same>)`
  — completing to the *display* string means the accepted buffer text is unambiguous (`#1 [person] Alice`),
  so mapping the submitted line back to an `Entity` is an exact dict lookup on a map the completer built,
  not a re-search. Keep that map on the completer instance and rebuild it each `get_completions` call.
- Construct the session with `complete_while_typing=True` and a `PromptSession` reused across loop
  iterations so history and rendering stay consistent.
- Cap what `search` is asked for (e.g. 15 results) so the completion menu stays a menu; the `limit`
  parameter added to `search_entities` exists for exactly this.
- Do not construct the session at `__init__` time — prompt-toolkit touches the terminal when a session is
  created. Build it lazily inside `pick`, the same way `TerminalEditorSession` resolves its editor command
  lazily inside `edit`, so wiring in `main.py` stays terminal-free.
- If `stdin` is not a TTY, do not attempt an interactive session: raise/propagate cleanly so the caller can
  skip the step (see the next task). prompt-toolkit will otherwise fail in a confusing way under pipes.
- For the unit tests: `prompt_toolkit.input.create_pipe_input()` plus
  `prompt_toolkit.output.DummyOutput()`, passed as `PromptSession(input=..., output=...)`, is the
  documented way to script a session in tests. That means `pick` should accept optional `input`/`output`
  overrides (constructor args are fine) rather than hardcoding the defaults.

Task: Add `DocumentService.link_document_interactive`
ACs:
- `DocumentService` takes an `IEntityPicker` and the entity search callable it needs in its constructor,
  alongside its existing dependencies.
- `link_document_interactive(document_id: int) -> list[Entity]` runs the picker for an **existing**
  document and links each selected entity to it, returning the entities that were newly linked, in
  selection order.
- A document id that doesn't exist raises `DocumentNotFoundError` **before** the picker is invoked — no
  prompt is ever shown for a document that can't be linked.
- Entities already linked to the document are skipped rather than double-linked, and are not included in
  the returned list.
- Linking an entity that no longer exists (deleted between search and submit) is skipped, not fatal: the
  remaining selections are still linked.
- If the picker raises `EntityPickerAbortedError`, it propagates unchanged; anything linked before the
  abort stays linked.
- The docstring's `Raises:` section names `DocumentNotFoundError` and `EntityPickerAbortedError` with the
  exact condition for each.
- Unit tested with a scripted fake `IEntityPicker` and fake dbs: no selections, several selections,
  already-linked entity, deleted entity, unknown document id, and aborted picker.
Implementation Notes:
- This is the whole feature. The `create` and `ingest` entry points in the next tasks are one call each
  into this method — no linking logic may live in either of them, and none may live in the controller.
- See `src/forte/service/document_service.py`. Follow the existing constructor-injection shape
  (`document_db`, `mention_db`, `entity_db`, `editor`, `document_searcher`) and add the picker as one more
  constructor dep.
- Reuse the existing `link_document` path rather than writing a second route to `mention_db`, so the
  entity-exists and document-exists validation stays in one place.
- Taking a document **id** (not a freshly created `Document`) is what makes it reusable: `create` and
  `ingest` both have an id by the time they call it, and the standalone command has nothing else.
- Return `list[Entity]`, not ids, so every caller can print `#<id> [<schema>] <name>` without a re-query.
- The search callable passed to the picker should exclude nothing — a user may deliberately want to see
  every entity. Already-linked entities are filtered at link time, not at search time, so the user isn't
  confused by a name that silently won't appear.

Task: Add the `forte doc link-interactive` CLI command and wiring
ACs:
- `forte doc link-interactive <id>` prints the document's id and name, runs the interactive prompt, and
  then prints the entities that were linked (one line each, `#<id> [<schema>] <name>`), or a note that
  none were.
- The shared `--vault <name>` option is supported, like every other `doc` subcommand.
- When stdin is not a TTY (piped input, CI, an agent driving the CLI), the command fails fast with a clear
  message pointing at `forte doc link <doc_id> <entity_id>` — it must not hang or crash.
- A vault with no entities prints a short "no entities to link" message and exits 0 without showing an
  empty completion menu.
- Aborting with Ctrl-C exits cleanly with a message reporting what was linked before the abort; no
  traceback.
- An unknown document id fails with a clean `ClickException`, and no prompt is shown.
- `forte doc --help` lists `link-interactive`, and `forte doc link-interactive --help` explains the
  type-to-search / empty-line-to-finish interaction.
- Controller unit tested against a mock `DocumentService`: linked output, no-links output, non-TTY, unknown
  id, and abort handling.
Implementation Notes:
- See `src/forte/controller/cli_document_controller.py`. Follow the established shape exactly: a nested
  `@doc.command("link-interactive")` callback that only unpacks CLI args and delegates to
  `controller._link_interactive(...)`, with all logic, error handling, and echoing in the private method.
  Call `self._select_vault(vault_name)` first, like every sibling method.
- Wrap the service call in `try/except (DocumentError, EntityError, EntityPickerError, VaultError)` →
  `click.ClickException(str(e))` — base classes only, never individual subclasses — and handle the aborted
  case specially so the message can report partial progress.
- TTY detection belongs in the controller (`sys.stdin.isatty()`), not the service or the client — it is a
  fact about how the CLI was invoked. The service and picker stay ignorant of it.
- The three "guard" behaviors (non-TTY, no entities in the vault, nothing linked) are needed identically by
  `create` and `ingest` in the next task. Factor them into one private controller helper (e.g.
  `_run_interactive_link(document_id) -> list[Entity]`) that all three commands call, so the guards can
  never drift apart.
- Command naming: `link-interactive` keeps it adjacent to `link`/`unlink` in `--help` output and reads as
  a variant of `link` rather than a separate concept. Click accepts the hyphen in the command name as
  given; only the python function name needs the underscore.
- Wiring in `src/forte/main.py`: construct `PromptToolkitEntityPicker()` in the 'doc' sub-commands block
  and pass it into `DocumentService`. `entity_service` is already constructed above that block, so binding
  `entity_service.search_entities` as the search callable needs no reordering.

Task: Offer the link step from `forte doc create` and `forte doc ingest`
ACs:
- After `forte doc create <name>` stores the document, it runs the same interactive link step, then prints
  the created doc's id and name plus the entities linked.
- After `forte doc ingest <path>` stores the document, it does the same.
- Both go through the shared controller helper from the previous task, which goes through
  `link_document_interactive` — neither command contains any linking or picker logic of its own.
- Both accept `--no-link` to skip the step entirely, preserving today's fully non-interactive behavior for
  scripts and agents; both skip it automatically (with a short message, exit 0) when stdin is not a TTY.
- The document is created/ingested **before** the prompt runs, so aborting the link step never loses the
  text the user just typed or the file they just ingested. On abort, the command reports the doc id and
  suggests `forte doc link-interactive <id>` to resume.
- `forte doc ingest` on a re-ingested (deduped) document still offers the link step against the existing
  document id, rather than skipping it.
- `forte doc create --help` and `forte doc ingest --help` document the second step and `--no-link`.
- Existing controller and e2e tests for both commands still pass, updated only where the new default
  behavior genuinely changed their observable output.
Implementation Notes:
- Expect this task to be small — if it isn't, logic has leaked out of `link_document_interactive` or the
  shared controller helper, and belongs back in one of them.
- `_create` already wraps its service call in `try/except (DocumentError, EditorError, VaultError)` →
  `click.ClickException(str(e))`; `_ingest` wraps `(DocumentError, VaultError)`. Add `EntityPickerError` to
  both tuples (base class only).
- "Persist first, link second" is the no-partial-work rule applied honestly: collecting links before
  writing would mean a Ctrl-C at the picker throws away a document the user already saved in their editor,
  which is precisely the friction this feature exists to remove.
- `AgentService` drives `DocumentService` directly, not the controller, so it never reaches the picker —
  but double-check no agent-side or scripted call path now lands in an interactive prompt. The service-layer
  `create_document` / `ingest_document` signatures should stay unchanged for exactly this reason: the
  interactive step is composed by the controller, not welded into them.

Task: Write the spec scenarios for interactive linking
ACs:
- [docs/spec/forte-doc.md](../../spec/forte-doc.md) gains a `forte doc link-interactive` section with
  Gherkin scenarios covering: typing a partial name and selecting the suggested entity; selecting several
  entities in one session; finishing with an empty line; entering text that matches nothing; selecting an
  entity already linked to the document; aborting mid-session; an unknown document id; a non-TTY stdin;
  and a vault with no entities.
- At least one scenario asserts the display format of a suggestion explicitly — `#1 [person] Alice`,
  showing id, type, and name.
- Scenarios state that after a successful session, `forte doc show <id>` lists the picked entities under
  "Mentions", and `forte entity show <entity_id>` lists the doc — i.e. the interactive step produces
  exactly the same links `forte doc link` would.
- The `forte doc create` and `forte doc ingest` sections each gain scenarios for the follow-on link step
  and for `--no-link`, written as "the same prompt described under `forte doc link-interactive`" rather
  than restating the whole interaction twice.
- The `link-interactive` section intro states that this is literal substring matching over entity names
  and aliases, distinct from the deferred semantic `entity search`.
- The file's opening paragraph, which enumerates the `forte doc` subcommands, is updated to include
  `link-interactive`, and to describe `create` and `ingest` as two-step (store, then link) flows.
Implementation Notes:
- Match the existing style of `docs/spec/forte-doc.md`: one `### Scenario: <title>` heading per scenario
  with a ```gherkin block, phrased purely in terms of what the user types and what the user observes.
- Phrase keystrokes at the level of intent — "When the user types `ali` and selects `#1 [person] Alice`" —
  rather than naming prompt-toolkit key bindings, so the spec survives a change of prompt library.
- The interaction is specified once, under `link-interactive`, and referenced from the other two. That
  mirrors how the code is factored and stops three copies of the same scenarios from drifting apart.
- Specs are the source of truth and drive the e2e tests: write these before or alongside the e2e task
  below and keep the two in lockstep.

Task: Add e2e tests for interactive linking
ACs:
- A new `tests/e2e/test_doc_link_interactive.py` covers the `forte doc link-interactive` scenarios above,
  driving the real CLI end to end.
- `tests/e2e/test_doc_create.py` and `tests/e2e/test_doc_crud.py` (ingest) each gain a test for the
  follow-on link step and one for `--no-link` — enough to prove the entry point is wired, without
  re-testing the interaction itself.
- The interactive tests run the CLI attached to a pseudo-terminal, feed keystrokes, and assert on what the
  user sees and on the resulting links (via `forte doc show <id>` output) — not on SQLite rows or internal
  APIs.
- Non-interactive paths are covered without a pty: `--no-link`, and plain piped stdin (which must skip the
  step for `create`/`ingest` and fail cleanly for `link-interactive`).
- Existing e2e tests still pass, updated only where the new default behavior genuinely changed their
  observable output.
- `pytest tests/e2e` passes.
Implementation Notes:
- Keep the harness conventions already in `tests/e2e/test_doc_create.py`: `FORTE_BIN` resolved from
  `sys.executable`, the `forte(args, home, env)` helper, `tmp_path`-scoped fake `HOME`, `a_vault(...)`, and
  `a_fake_editor(...)` for the editor step. Gherkin-style `# Given:` / `# When:` / `# Then:` comments with a
  `# Scenario: <title>` comment above each test.
- The pty helper is needed by three test files, so put it somewhere shared (a `tests/e2e/conftest.py`
  fixture or a small helper module) rather than copy-pasting it. Stdlib `pty.openpty()` +
  `subprocess.run(stdin=slave, ...)` is enough; `pexpect` is fine too if you'd rather take the dev-only
  dependency. Either way it stays in one place so the tests themselves read as keystrokes in, text out.
- Give every pty-driven test a timeout so a mis-specified interaction fails the suite instead of hanging
  CI forever.
- Seed each test's vault with a handful of entities across two schemas, with deliberately overlapping name
  prefixes (`Alice`, `Alice Nguyen`, `Alignment Health`), so ranking and the multi-select loop are actually
  exercised rather than trivially satisfied.
- Terminal escape sequences will be in the captured output; assert on substrings (`#1 [person] Alice`)
  rather than exact-matching whole screens.

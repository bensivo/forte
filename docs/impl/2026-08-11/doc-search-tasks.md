# `forte doc search` — Task Breakdown

Feature: remove the "I have to `grep` the vault by hand" friction (step 8 of
[tmp/docs/raw/2026-08-10-friction-points.md](../../../tmp/docs/raw/2026-08-10-friction-points.md)) by adding
full-text search over document contents — the VSCode/Obsidian search experience, not semantic search.

`forte doc search "<text>"` scans the text of every document in the vault and prints every matching line,
grouped under the document it came from:

```
doc #3: Acme Kickoff Notes
  line 12: we agreed the launch date is March 4th
  line 47: launch date moved, pending Acme signoff

doc #7:  Weekly Sync 2026-07-02
  line 3: launch date is still the open question
```

This is deliberately **not** the deferred semantic `entity search` from
[docs/solution-design.md](../../solution-design.md) — it is literal/regex matching over document bodies,
with no LLM, no embeddings, and no network calls.

Tasks:
- Add the search result models and error type to `model/document.py`
- Define the `IDocumentSearcher` interface
- Implement `FsDocumentSearcher` over `docs/processed/`
- Add `DocumentService.search_documents`
- Add the `forte doc search` CLI command and wiring
- Write the `forte doc search` spec scenarios
- Add e2e tests for `forte doc search`

---

Task: Add the search result models and error type to `model/document.py`
ACs:
- `model/document.py` gains two pure dataclasses:
  - `DocumentMatch` — one matching line within a document: `line_number: int`, `line: str`, and the
    match spans within that line (e.g. `spans: list[tuple[int, int]]`) so a caller can highlight hits.
  - `DocumentSearchResult` — one document and all of its matches: `document: Document`,
    `matches: list[DocumentMatch]`.
- `line_number` is 1-based and counts lines of the document's **body text**, not lines of the processed
  markdown file — so line 1 is the first line the user would see in `forte doc show`, not the `---` of
  the frontmatter.
- A new `InvalidSearchQueryError(DocumentError)` is defined, with a docstring naming the one condition
  that raises it (an empty/whitespace-only query, or a malformed regex when `--regex` is used).
- Both dataclasses have class docstrings; no filesystem or DB I/O in this module (it stays pure data).
Implementation Notes:
- Style guide: each feature defines its exceptions in its `model/` file, one base class per feature plus
  subclasses. Search is part of the document feature, so it reuses the existing `DocumentError` base and
  lives in `src/forte/model/document.py` alongside `DocumentNotFoundError` etc. — do not create a new
  base class or a new feature module.
- Keep `spans` even though the first CLI version may only underline/bold them or ignore them; it is the
  difference between "we can highlight later" and "re-run the regex in the controller".
- The `Document` inside `DocumentSearchResult` is the full record, so the controller can print
  `#<id>  <name>` without a second lookup.

Task: Define the `IDocumentSearcher` interface
ACs:
- `interface/document_searcher.py` defines `IDocumentSearcher` with a single method, e.g.
  `search(pattern: re.Pattern, limit_per_document: int | None) -> list[tuple[int, list[DocumentMatch]]]`
  returning, per document id, the matching lines found in that document's stored text.
- The docstring describes an IO/scan operation only: no validation, no `Raises:` section, no business
  logic, no query parsing (the compiled pattern is handed in by the service).
- The interface knows nothing about output formatting, grouping order, or result limits beyond the
  per-document cap it is given.
Implementation Notes:
- Style guide: interfaces are named `I<Noun>`, describe storage/IO operations only, and their methods
  don't raise feature errors. See `src/forte/interface/document_db.py` for the shape to match.
- Why a separate interface rather than another `IDocumentDb` method: `IDocumentDb` is the
  record store (rows + raw/processed copies), and a full-text scanner is a different kind of dependency
  with a different implementation strategy. Keeping it separate is what makes it swappable — a future
  `RipgrepDocumentSearcher` (shelling out to `rg`) or `SqliteFtsDocumentSearcher` (FTS5 virtual table)
  can drop in with zero service changes if the pure-python scan ever gets too slow.
- Returning ids (not `Document` records) keeps the client out of the business of joining to metadata;
  the service does that join via `IDocumentDb`.
- Taking a pre-compiled `re.Pattern` means case-sensitivity, whole-word, and literal-vs-regex are all
  decided once in the service and the client just applies the pattern.

Task: Implement `FsDocumentSearcher` over `docs/processed/`
ACs:
- `client/fs_document_searcher.py` defines `FsDocumentSearcher(IDocumentSearcher)`, constructed with the
  shared `VaultContext` (like `SqliteDocumentDb`), resolving the vault root lazily on each call.
- `search` walks `docs/processed/*.md`, derives each file's document id from its filename stem, strips the
  YAML frontmatter, and returns every body line matching the pattern with a 1-based body-relative
  line number and the match spans on that line.
- Files whose stem isn't an integer, and files that fail to parse or decode, are skipped rather than
  crashing the whole search.
- `limit_per_document`, when given, stops collecting matches for a document after that many hits (the
  scan of that file can stop early).
- A vault with no `docs/processed/` directory returns an empty list rather than raising.
- Reasonable performance on a realistic vault: a few thousand documents scan in well under a second.
  Read files once, match line-by-line with the compiled pattern, and don't build intermediate copies of
  whole files beyond the read itself.
Implementation Notes:
- See `src/forte/client/sqlite_document_db.py` for the `VaultContext` → `VaultLayout` pattern
  (`self._context.get_root()`, `VaultLayout(root)`, `layout.docs_processed_dir`). Reuse it exactly;
  the searcher must never resolve a vault at construction time.
- The processed copy is written as `docs/processed/<id>.md` (see `_insert_document`), so the stem *is*
  the document id — no DB round-trip needed to map file → document. Guard the `int()` conversion anyway.
- Frontmatter stripping: `forte.model.document_markdown.from_markdown(text)` already returns a
  `ParsedDocument` with a `.body`. Prefer it over hand-rolling a `---` split, and note that it `.strip()`s
  the body — line numbers must be computed against that same stripped body so they agree with what
  `forte doc show` prints. If `from_markdown` raises `ValueError` on a malformed file, skip that file.
- Search the **processed** text, not the raw copies: raw copies may be PDFs/docx binaries, while
  processed copies are always extracted plain text. That is exactly why the extraction step exists.
- Deliberately pure python, no `rg` subprocess: forte can't assume ripgrep is installed, and Python's
  `re` over already-in-memory lines is fast enough at this scale. Say this in the class docstring so it
  doesn't read as an oversight, and name the swap path (the interface) in the same breath.
- No third-party search dependency either. PyPI's `ripgrep` package bundles the binary but ships wheels
  for only macos-arm64 and manylinux-x86_64 (everyone else needs a Rust toolchain); `rgpy` is a single
  macos-arm64 wheel with one release; `ripgrepy` just wraps an `rg` you already installed. None of them
  are worth narrowing forte's install matrix for.
- Measured baseline on a deliberately oversized vault (3,000 docs / 65 MB, term matching every document):
  pure-python scan ~510 ms single-threaded, vs ~97 ms for `rg` at 326% CPU. The gap is thread
  parallelism, not match speed — the python run is I/O-bound on reading the files. A realistic vault
  lands in the tens of milliseconds. Treat "noticeably slower than this on a normal vault" as the signal
  that something is wrong with the implementation, not that python is the wrong tool.
- Cheap win, since I/O dominates: run `pattern.search(whole_text)` once per file and only fall through to
  the line-by-line loop (which builds `DocumentMatch` objects and spans) when that hits. Most files fail
  the prefilter for a typical query, so the per-line work is skipped entirely for them.
- Client-level unit tests are expected here (style guide: "clients should be unit tested as much as is
  reasonable") — a `tmp_path` vault with a couple of hand-written processed files is enough.

Task: Add `DocumentService.search_documents`
ACs:
- `DocumentService` takes an `IDocumentSearcher` in its constructor alongside its existing dependencies.
- `DocumentService.search_documents(query, *, case_sensitive=False, regex=False, limit_per_document=None)
  -> list[DocumentSearchResult]` validates the query, compiles it into a pattern, delegates the scan to
  the searcher, joins each returned id to its `Document` via `document_db`, and returns results ordered
  by document id with each document's matches in ascending line order.
- Default behavior is a **literal, case-insensitive substring** match: the query is `re.escape`d unless
  `regex=True`, and `re.IGNORECASE` is applied unless `case_sensitive=True`.
- An empty or whitespace-only query raises `InvalidSearchQueryError`; with `regex=True`, a pattern that
  fails to compile raises `InvalidSearchQueryError` with the underlying `re.error` message included.
- All validation happens before the searcher is called, per the style guide's no-partial-work rule.
- Documents returned by the searcher that have no matching row in `document_db` (an orphaned processed
  file) are dropped from the results rather than raising.
- The docstring's `Raises:` section names `InvalidSearchQueryError` and the exact condition for each way
  it can be raised.
- Unit tested with a fake `IDocumentSearcher` and fake `IDocumentDb`: literal match, case sensitivity on
  and off, regex mode, regex compile failure, empty query, per-document limit, ordering, and the
  orphaned-file case.
Implementation Notes:
- See `src/forte/service/document_service.py`. Follow the existing constructor-injection shape
  (`document_db`, `mention_db`, `entity_db`, `editor`) and add the searcher as one more constructor dep.
- Case-insensitive-by-default matches what users expect from Obsidian/VSCode search; the escape-unless-
  regex default means a query like `v1.2 (draft)` does the obvious thing instead of erroring or
  silently matching too much.
- Consider a `--word`/whole-word option only if it falls out for free (`\b` wrapping); it is not required
  for this batch.
- The join is `document_db.get(id)` per hit, or one `document_db.list()` into a dict when there are many
  hits — either is fine; a dict keyed by id keeps it O(n) and reads cleanly.
- No new interface method on `IDocumentDb` is needed.

Task: Add the `forte doc search` CLI command and wiring
ACs:
- `forte doc search "<text>"` prints results grouped by document: a header line per document
  (`#<id>  <name>`), then one indented line per match showing the line number and the matching line
  text, then a blank line between documents.
- A trailing summary line reports the totals, e.g. `2 documents, 3 matches`.
- When nothing matches, the command prints a clear message (e.g. `No matches.`) and exits 0 — no match
  is not an error.
- Options: `--case-sensitive/-s` (default off), `--regex/-r` (default off, treat the query literally),
  `--limit/-n <int>` (max matches shown per document), and the shared `--vault <name>`.
- Long matching lines are truncated to keep output scannable in a terminal (e.g. around the first match,
  with an ellipsis), so a one-line 50KB PDF extract doesn't flood the screen.
- An empty query or an invalid regex fails with a clean `ClickException` message, not a traceback.
- `forte doc --help` lists `search`, and `forte doc search --help` documents the literal-by-default
  behavior and the `--regex` escape hatch.
- Controller unit tested against a mock `DocumentService` (grouped output, empty results, error mapping).
Implementation Notes:
- See `src/forte/controller/cli_document_controller.py`. Follow the established shape exactly: a nested
  `@doc.command("search")` callback that only unpacks CLI args and delegates to `controller._search(...)`,
  with all logic, error handling, and echoing in the private method.
- `_search` calls `self._select_vault(vault_name)` first, like every sibling method, and wraps the service
  call in `try/except (DocumentError, VaultError)` → `click.ClickException(str(e))` — base classes only,
  never individual subclasses.
- Right-align line numbers within a document group so the match text lines up (see the example at the top
  of this file); `click.echo` is the only output mechanism used in this controller.
- Optional polish, only if it stays simple: use `click.style` to bold the matched spans (the
  `DocumentMatch.spans` field exists for this) and dim the line numbers. Click already disables styling
  when stdout isn't a TTY, so piping into `grep`/`less` stays clean.
- Wiring in `src/forte/main.py`: construct `FsDocumentSearcher(vault_context)` in the 'doc' sub-commands
  block and pass it into `DocumentService`, next to `document_db`/`mention_db`/`entity_db`/`editor`.
  `AgentService` receives the same `document_service` instance, so no agent-side changes are needed.

Task: Write the `forte doc search` spec scenarios
ACs:
- [docs/spec/forte-doc.md](../../spec/forte-doc.md) gains a `forte doc search` section with Gherkin
  scenarios covering: a match in a single document; matches across multiple documents grouped by
  document; case-insensitive default; `--case-sensitive`; `--regex` and literal-by-default (e.g. a query
  containing `.` or `(`); `--limit`; no matches found; empty query; invalid regex; and search scoped to
  the vault selected by `--vault`.
- The section's intro states explicitly that this is literal/regex full-text search over document bodies,
  distinct from the deferred semantic `entity search`.
- The file's opening paragraph, which enumerates the `forte doc` subcommands, is updated to include
  `search` (and `create`, if it is still missing there).
Implementation Notes:
- Match the existing style of `docs/spec/forte-doc.md`: one `### Scenario: <title>` heading per scenario
  with a ```gherkin block, phrased in terms of what the user runs and what the user observes.
- Specs are the source of truth for behavior and drive the e2e tests, so write this task's scenarios
  before (or alongside) the e2e test task below, and keep the two in lockstep.

Task: Add e2e tests for `forte doc search`
ACs:
- A new `tests/e2e/test_doc_search.py` covers one test per spec scenario above.
- Tests assert only on things a user can observe: exit codes, stdout content, and files in the vault
  directory — no SQLite assertions and no internal-API calls.
- Searching finds text in documents ingested from `.md`, and in a document created via `forte doc create`
  (both paths write a processed copy, so both must be searchable).
- Text that appears only in a document's *frontmatter* (e.g. the source path) does not produce a body
  match, and reported line numbers correspond to the body lines shown by `forte doc show`.
- `pytest tests/e2e/test_doc_search.py` passes, and the existing e2e suite still passes.
Implementation Notes:
- Copy the harness conventions from `tests/e2e/test_doc_crud.py`: `FORTE_BIN` resolved from
  `sys.executable`, the `forte(args, home)` helper, `tmp_path`-scoped fake `HOME`, and the
  `a_vault(tmp_path)` setup helper.
- Use gherkin-style `# Given:` / `# When:` / `# Then:` comments per block, with a `# Scenario: <title>`
  comment above each test naming the matching spec scenario.
- The `forte` helper `shlex.split`s its argument string, so a quoted query (`doc search "launch date"`)
  survives as one argument — same trick `--name "Kickoff Notes"` already relies on.
- Ingest two or three small fixture documents with deliberately overlapping and non-overlapping terms so
  the grouping, ordering, and totals in the output are actually exercised.

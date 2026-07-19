# `forte doc ingest/list/show/link` — Tasks

Feature: Implement `forte doc ingest`, `forte doc list`, `forte doc show`, and `forte doc link` per PRD ("Document ingest", UJ1/UJ2/UJ3) and solution-design.md ("Vault Folder Structure", "SQLite Schema (draft)", "Ingest Pipeline"). **Scope cut for this batch: no entity extraction, no entity linking, no field extraction, and no review TUI.** `doc ingest` in this batch does only pipeline step 1 (copy into `docs/raw/`) plus a new "extract raw text" step that writes the doc's text into `docs/processed/` with metadata frontmatter, then stops — it does not call the LLM at all. Entity extraction/linking (solution-design's steps 2-5, `ingest_changes`, and the TUI) are explicitly deferred to a future batch.

Because entity extraction is deferred but linking a doc to an entity is still a PRD-adjacent need, this batch also adds two manual commands, `forte doc link <id> <entity-id>` and `forte doc unlink <id> <entity-id>`, so a user (or agent) can hand-link/unlink a processed doc and an existing entity without waiting on automatic extraction. These directly create/remove rows in `mentions` without going through the (not-yet-built) proposal/approval flow.

The defining constraint that separates docs from entities: **documents are NOT dual-written as structured, editable knowledge like entities are.** A doc has exactly two on-disk artifacts — the immutable raw copy (`docs/raw/`) and a derived processed copy (`docs/processed/`) — plus one SQLite row in `documents`. There's no frontmatter *editing* story for docs; `processed/` is regenerated output, not something a user hand-maintains the way they do entity files. Docs are identified by the same auto-increment integer id convention as entities, in their own `documents` table.

- Write `forte doc` behavior spec
- Implement Document domain model + processed-markdown serialization
- Implement text extraction (md/txt/docx/pdf plain-text)
- Implement Document DB repository (dual-write raw copy + processed markdown + SQLite)
- Implement Mention DB repository (doc-entity link rows)
- Implement doc service layer (ingest / list / show / link / unlink)
- Wire `forte doc ingest` command and the `doc` group
- Wire `forte doc list` command
- Wire `forte doc show` command
- Wire `forte doc link` command
- Wire `forte doc unlink` command

---

Task: Write `forte doc` behavior spec
ACs:
- A new spec file `docs/spec/forte-doc.md` exists, following the structure of `docs/spec/forte-schema.md` (title + short intro paragraph, `## Scenarios` with Gherkin blocks, `## Out of scope`).
- Scenarios cover, at minimum:
  - `doc ingest <path>` on a valid `.md`/`.txt` file in a vault: prints a success message including the assigned integer id, exits 0, copies the source into `docs/raw/`, writes an extracted-text file into `docs/processed/` with metadata frontmatter (source path, content hash, ingested timestamp), and inserts a row in the `documents` table.
  - `doc ingest <path>` on a `.docx`/`.pdf` file: text is extracted before being written to `docs/processed/` (verbatim readable text, not raw binary).
  - `doc ingest <path>` where `<path>` does not exist exits non-zero with a clear error and writes nothing.
  - `doc ingest <path>` on a file type Forte doesn't know how to extract text from (e.g. `.png`) exits non-zero with a clear error and writes nothing.
  - `doc ingest <path>` run twice on the **same unchanged file** (same source path + content hash) is idempotent in a defined way — pick and document one behavior (e.g. re-running is a no-op that reports the existing doc id, OR errors telling the user it's already ingested) and keep it consistent with the "Ingest identity" note in solution-design.md.
  - `doc list` on a vault with several ingested docs prints one line per doc including its id and source filename; an empty vault prints a friendly "no docs" message and exits 0.
  - `doc show <id>` prints the doc's id, source path, ingested timestamp, and its extracted text (or a path to it); showing a non-existent id exits non-zero with a clear error.
  - `doc link <id> <entity-id>` on a valid doc id and entity id succeeds, prints confirmation, exits 0, and creates a row in `mentions`; the link is subsequently visible when showing the doc's mentions (see out-of-scope note on `doc show` mention display).
  - `doc link` with a non-existent doc id, or a non-existent entity id, exits non-zero with a clear error and creates no row.
  - `doc link` called twice with the same doc/entity pair — pick and document a behavior (idempotent no-op vs. duplicate row vs. error); keep it simple and consistent.
  - `doc unlink <id> <entity-id>` on a linked pair removes the `mentions` row, prints confirmation, exits 0, and the link no longer appears in `doc show`.
  - `doc unlink` on a doc/entity pair that is **not** linked — pick and document a behavior (idempotent no-op vs. error); keep it consistent with the `doc link` duplicate-call decision.
  - `doc unlink` with a non-existent doc id or entity id exits non-zero with a clear error.
  - Any `doc` subcommand run **outside a vault** (no `.forte/` found walking up) exits non-zero with the shared "Not inside a Forte vault" error and does nothing.
Implementation Notes:
- Specs are the source of truth per CLAUDE.md and drive the integration tests written in the command tasks. Write this first so the command tasks have concrete assertions.
- Keep scenarios black-box: observable CLI behavior (stdout, exit code, on-disk files, DB row state) — mirror `forte-schema.md`/`forte-entity.md`, not internal function calls.
- Put explicitly **out of scope**: entity extraction from doc content, entity linking proposals, field extraction, the review TUI, `ingest_changes` / resumable ingest, `--yes` auto-approve flag (nothing to approve yet), `doc show` displaying full mention/entity details beyond a bare list of linked entity ids (deferred richer display), `forte doc remove` (not requested), OCR/audio/web/email ingestion.
- Nail down the exact re-ingest and duplicate-link behaviors with the corresponding implementation tasks and keep the spec consistent with whatever is chosen.

Task: Implement Document domain model + processed-markdown serialization
ACs:
- Domain layer: `src/forte/domain/document.py` exports a `Document` model with: `id: int | None`, `source_path: str` (original path as given by the user, or vault-relative raw path — decide and document), `content_hash: str`, `raw_path: str | None` (vault-relative path under `docs/raw/`), `processed_path: str | None` (vault-relative path under `docs/processed/`), `ingested_at: str` (ISO-8601 timestamp), `status: str` (e.g. `"processed"` — a simple literal for this batch since there's no multi-step pipeline yet).
- A serialization module `src/forte/domain/document_markdown.py` provides `to_markdown(document, text) -> str`, rendering YAML frontmatter (`source_path`, `content_hash`, `ingested_at`) followed by the extracted text as the body, and `from_markdown(text) -> ParsedDocument` parsing frontmatter + body back apart. Mirrors `entity_markdown.py`'s pattern (frontmatter + body split via `pyyaml`, already a dependency after the entity batch).
- A small helper computes `content_hash` from file bytes (e.g. `hashlib.sha256`), reused by both the ingest path and any future identity checks.
- Unit tests cover round-trip of `to_markdown`/`from_markdown`, and hash stability for identical content.
Implementation Notes:
- This is the domain layer — pure, no filesystem or DB I/O beyond the hash helper operating on bytes already in memory. The repository (later task) owns actually reading the source file and writing files to disk.
- Per solution-design, "mentions" listing entity ids linked to a doc is **frontmatter on processed docs** in the long run, but since extraction/linking isn't implemented yet in this batch, processed-doc frontmatter carries no `mentions` field yet — `doc link` (a separate task) writes directly to the `mentions` DB table instead of touching this frontmatter. Note this gap plainly in a code comment so a future batch knows to reconcile it.

Task: Implement text extraction (md/txt/docx/pdf plain-text)
ACs:
- `src/forte/services/text_extraction.py` (or similar) exposes `extract_text(path: Path) -> str`, dispatching on file extension: `.md`/`.txt` read as plain UTF-8 text; `.docx` via `python-docx`; `.pdf` via `pypdf` (text-only, per solution-design's "Doc parsing" tech choices).
- Unsupported extensions raise a typed `UnsupportedFileTypeError` with a clear message naming the extension.
- Unit tests cover `.md`/`.txt` extraction, and at least one `.docx` and one `.pdf` fixture (small fixture files committed under a test-fixtures folder) producing non-empty extracted text; an unsupported extension (e.g. `.png`) raises the typed error.
Implementation Notes:
- Add `python-docx` and `pypdf` to `pyproject.toml` dependencies (solution-design already names them; they are not yet present per the current dependency set used by entity/schema batches — verify and add if missing). Flag this dependency addition in the PR.
- Keep this a pure function of a file path to a string — no vault/DB knowledge — so the doc service can call it without coupling extraction logic to ingest orchestration.
- For `.docx`, join paragraph text with newlines; for `.pdf`, join per-page extracted text with a page-break marker or blank line — pick one, document it in a docstring since exact formatting isn't specified elsewhere.

Task: Implement Document DB repository (dual-write raw copy + processed markdown + SQLite)
ACs:
- DB layer: `src/forte/db/document_repository.py` exposes a repository over an open vault (`root: Path`) providing:
  - `add(source_path: Path, content_hash: str, extracted_text: str) -> Document` — copies the source file into `docs/raw/<original-filename>` (disambiguating on name collision, mirroring the entity repo's collision handling), writes the processed markdown (frontmatter + extracted text) into `docs/processed/<slug-or-id>.md`, inserts the `documents` row (`source_path`, `content_hash`, `raw_path`, `processed_path`, `ingested_at`, `status`), and returns the `Document` with its assigned `id` and both paths populated.
  - `get(id: int) -> Document | None` — single lookup by id.
  - `list() -> list[Document]` — all documents, ordered by id.
  - `find_by_identity(source_path: str, content_hash: str) -> Document | None` — supports the re-ingest idempotency check (solution-design's "Ingest identity" = source path + content hash).
- Integration tests against a temp vault (real SQLite + real files) assert: after `add`, both the raw copy and the processed markdown file exist at their expected paths, the processed file's frontmatter matches, and the row is present with the returned id; `get`/`list` round-trip; `find_by_identity` finds an exact prior ingest and returns `None` for a novel one.
- Follow the existing repo style: stdlib `sqlite3`, one connection per operation (see `db/entity_repository.py`, `db/schema_repository.py`).
Implementation Notes:
- The `documents(id, source_path, content_hash, raw_path, processed_path, ingested_at, status)` table already exists from the `forte init` bootstrap (`src/forte/db/schema.py`) — read/write it, don't redefine it.
- Derive paths via `VaultLayout(root)` (check `domain/vault.py` for existing `raw_dir`/`processed_dir`-style accessors; add them there if the entity/schema batches didn't already, following whatever pattern `entities_dir` used).
- `raw_path`/`processed_path` stored in the DB should be **vault-relative**, matching the convention `file_path` used for entities.
- Processed filename: use the id (only known after the DB insert) or a slug of the source filename plus a disambiguator — pick one and be consistent; since the id is only known post-insert, either write processed markdown after obtaining `lastrowid` and then `UPDATE` the row's `processed_path`, or slug from the source filename with the same collision-disambiguation approach as the entity repo. Document the choice in a code comment since it's a genuine design fork.
- Use `shutil.copy2` (or similar) for the raw copy to preserve mtime/content faithfully.

Task: Implement Mention DB repository (doc-entity link rows)
ACs:
- DB layer: `src/forte/db/mention_repository.py` exposes a repository over an open vault (`root: Path`) providing:
  - `add(doc_id: int, entity_id: int, quote: str = "") -> None` — inserts a row into `mentions` (`doc_id`, `entity_id`, `quote`, `created_at`).
  - `remove(doc_id: int, entity_id: int) -> None` — deletes the row(s) matching that doc/entity pair from `mentions`.
  - `list_for_doc(doc_id: int) -> list[Mention]` — all mentions for a given doc.
  - `exists(doc_id: int, entity_id: int) -> bool` — used to implement whatever duplicate-link/unlink behavior the spec settles on.
- A small `Mention` domain model (`src/forte/domain/mention.py`) with `doc_id: int`, `entity_id: int`, `quote: str`, `created_at: str`.
- Integration tests: `add` creates a row visible via `list_for_doc`; `exists` correctly reports true/false; `remove` deletes the row so it no longer appears in `list_for_doc`/`exists`; removing a non-existent pair is a safe no-op (deletes zero rows, does not raise); adding for a doc with no prior mentions then listing returns exactly the one row.
Implementation Notes:
- `mentions(doc_id, entity_id, quote, created_at)` table already exists from the `forte init` bootstrap — no schema changes needed. `quote` is optional/empty for manually-created links from `doc link` (no supporting text from an LLM extraction in this batch).
- Keep this repository doc/entity-extraction-agnostic — it just persists link rows regardless of how they were proposed (manually via `doc link` now, or automatically via a future extraction pipeline).

Task: Implement doc service layer (ingest / list / show / link / unlink)
ACs:
- `src/forte/services/document.py` exposes `ingest_document`, `list_documents`, `get_document`, `link_document`, and `unlink_document`, each taking the vault root and orchestrating validation + the repositories above.
- `ingest_document(root, path)`:
  - Raises a typed error if `path` does not exist.
  - Computes the content hash and extracts text via `text_extraction.extract_text` (raising the typed `UnsupportedFileTypeError` through, or wrapping it — pick one and be consistent).
  - Checks `DocumentRepository.find_by_identity(source_path, content_hash)`; if found, applies whatever idempotency behavior the spec settled on (return existing doc without re-writing, or raise a typed "already ingested" error) — do not silently duplicate.
  - Otherwise calls `DocumentRepository.add` and returns the new `Document`.
- `list_documents(root)` returns all documents.
- `get_document(root, id)` returns the document or raises a typed "not found" error.
- `link_document(root, doc_id, entity_id)`:
  - Raises "not found" if the doc id doesn't exist (via `DocumentRepository.get`) or the entity id doesn't exist (via `EntityRepository.get`, reused from the entity batch).
  - Applies the spec's chosen duplicate-link behavior using `MentionRepository.exists`.
  - Otherwise calls `MentionRepository.add`.
- `unlink_document(root, doc_id, entity_id)`:
  - Raises "not found" if the doc id doesn't exist or the entity id doesn't exist (same lookups as `link_document`).
  - Applies the spec's chosen not-linked behavior (no-op vs. error) using `MentionRepository.exists`.
  - Otherwise calls `MentionRepository.remove`.
- Typed exceptions (e.g. `DocumentNotFoundError`, `UnsupportedFileTypeError` re-exported/wrapped, `SourceFileNotFoundError`, `AlreadyIngestedError` if that's the chosen behavior) so the driver maps each to a `click.ClickException` — mirrors `services/entity.py` / `services/schema.py`.
- Unit/integration tests cover each validation branch (missing source file, unsupported type, duplicate ingest, not-found on show/link/unlink, not-found entity on link/unlink, duplicate link, unlink of a not-linked pair) and the happy paths.
Implementation Notes:
- No entity extraction, no LLM calls, no `ingest_changes` rows, no TUI — this service is deliberately thin for this batch: copy + extract + record, full stop.
- Keep all business logic here, not in the Click commands, matching the established layering (driver has no business logic).
- `link_document`/`unlink_document` deliberately bypass any "proposed change" concept — they're direct, immediate writes, since there's no extraction pipeline yet to propose or retract links in the first place.

Task: Wire `forte doc ingest` command and the `doc` group
ACs:
- `forte.cli` gains a `doc` Click **group** registered under the top-level `main` group, and an `ingest` subcommand: `forte doc ingest <path>`.
- `<path>` is a positional argument (a filesystem path, not required to be inside the vault — the source file being ingested is separate from the vault the command is run in).
- Resolves the vault via `find_vault_root(Path.cwd())`, calls `services.document.ingest_document`, and on success prints a one-line confirmation including the assigned id (e.g. `Ingested doc #7: kickoff.md`) and exits 0.
- Outside a vault → non-zero exit with the shared discovery error. Service errors (source file not found, unsupported type, already-ingested per the chosen behavior) → `click.ClickException`, non-zero exit, no partial writes.
- Integration test uses `CliRunner` + `isolated_filesystem()`: `forte init`, create a small `.md` fixture file, `forte doc ingest <file>`, and assert the doc is stored (visible via follow-up `doc list`/`doc show`, both raw and processed files exist, and the DB row is present). A second test asserts re-running ingest on the identical file behaves per the spec's chosen idempotency rule.
- This task lands the `doc` group, so it must merge before the `list`/`show`/`link` command tasks (they attach to the same group).
Implementation Notes:
- Follow the driver pattern in `src/forte/cli/__init__.py` (or a split `cli/doc.py` module if the entity batch already split per-group — match whatever convention landed there): thin command, `try/except` mapping typed errors to `click.ClickException(str(e))`.
- No `--yes` flag in this batch — there is nothing to approve yet (deferred with the TUI).
- Use `Path.cwd()` as the discovery start; `<path>` itself should be resolved relative to the caller's original cwd, not the vault root — be careful if `find_vault_root` changes directories anywhere (it shouldn't, but verify).

Task: Wire `forte doc list` command
ACs:
- `forte doc list` prints one line per document including its id and source filename. On a vault with no docs it prints a friendly message (e.g. `No documents yet.`) and exits 0.
- Resolves the vault via discovery; outside a vault exits non-zero with the shared error.
- Integration test ingests two docs, asserts both appear in `doc list`; plus an empty-vault message test.
Implementation Notes:
- Plain `click.echo` lines are fine (e.g. `#7  kickoff.md`), matching `entity list`'s style.
- Depends on the `doc` group existing (ingest-command task).

Task: Wire `forte doc show` command
ACs:
- `forte doc show <id>` prints the doc's id, source path, ingested timestamp, and its extracted text (either inline or by printing the `docs/processed/` path for the user to open — pick one, per the spec).
- Also prints linked entities (mentions) if any exist for the doc, even though nothing in this batch creates them automatically — the display should already work once `doc link` (a later task) adds rows.
- Showing a non-existent id exits non-zero with a clear "not found" error.
- Resolves the vault via discovery; outside a vault exits non-zero.
- Integration test ingests a doc, then asserts `doc show <id>` output contains the source filename and the extracted text (or its file path per the design choice); a follow-up test (after `doc link` lands) asserts a linked entity id appears in `doc show` output.
Implementation Notes:
- Read via `services.document.get_document`; map `DocumentNotFoundError` to `click.ClickException`.
- `<id>` is an integer argument (`type=int`).
- Fetch mentions via `MentionRepository.list_for_doc` directly from the command, or add a small service helper — keep it simple since there's no entity-detail hydration required yet (id list is enough for this batch, per the doc-spec's out-of-scope note on richer mention display).

Task: Wire `forte doc link` command
ACs:
- `forte doc link <id> <entity-id>` links an existing document to an existing entity by creating a `mentions` row.
- On success prints a one-line confirmation (e.g. `Linked doc #7 to entity #3`) and exits 0.
- Non-existent doc id, or non-existent entity id, exits non-zero with a clear "not found" error identifying which one, and creates no row.
- Re-linking the same doc/entity pair behaves per the spec's chosen duplicate rule.
- Outside a vault exits non-zero.
- Integration test: ingest a doc and add an entity, `doc link <doc-id> <entity-id>`, then assert `doc show <doc-id>` reflects the link; a second test asserts linking with an unknown doc id or unknown entity id errors and creates nothing; a third test covers the duplicate-link case per the chosen behavior.
Implementation Notes:
- Both `<id>` (doc) and `<entity-id>` are integer arguments (`type=int`).
- Map `services.document.DocumentNotFoundError` / the entity-not-found case (reuse `services.entity.EntityNotFoundError` if `link_document` raises it directly, or wrap it — keep consistent with how the service task decided to surface entity-not-found) to `click.ClickException`.
- Depends on the `doc` group existing.

Task: Wire `forte doc unlink` command
ACs:
- `forte doc unlink <id> <entity-id>` removes an existing link between a document and an entity by deleting the matching `mentions` row.
- On success prints a one-line confirmation (e.g. `Unlinked doc #7 from entity #3`) and exits 0.
- Non-existent doc id, or non-existent entity id, exits non-zero with a clear "not found" error identifying which one.
- Unlinking a pair that isn't currently linked behaves per the spec's chosen not-linked rule (no-op vs. error) — kept consistent with `doc link`'s duplicate-call behavior.
- Outside a vault exits non-zero.
- Integration test: ingest a doc, add an entity, `doc link <doc-id> <entity-id>`, then `doc unlink <doc-id> <entity-id>`, and assert `doc show <doc-id>` no longer shows the link; a second test asserts unlinking with an unknown doc id or unknown entity id errors; a third test covers unlinking a pair that was never linked, per the chosen behavior.
Implementation Notes:
- Both `<id>` (doc) and `<entity-id>` are integer arguments (`type=int`).
- Map `services.document.DocumentNotFoundError` / the entity-not-found case to `click.ClickException`, mirroring the `doc link` command's error mapping.
- Depends on the `doc` group existing (and pairs naturally with the `doc link` task — consider landing them together since they share the same service-layer task).

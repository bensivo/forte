# `forte entity` add/list/show/edit/remove — Tasks

Feature: Implement basic CRUD for the `forte entity` command group — `add`, `list`, `show`, `edit`, `remove` — per PRD ("Entities", UJ1/UJ2) and solution-design.md ("Vault Folder Structure", "File conventions", "IDs", "Schemas", "SQLite Schema"). End state: a user in an existing vault can manually create an entity of a defined schema, list entities (optionally filtered by schema), show a single entity, edit its fields and aliases, and remove it. **`forte entity search` is out of scope for this batch** (it depends on the deferred embeddings decision).

The defining constraint that separates entities from schemas: **entities are part of the human-readable knowledge base, so every write dual-writes to a markdown file (YAML frontmatter + free-form body) AND the SQLite `entities` table.** Schemas were SQLite-authoritative; entities are authoritatively stored in *both* markdown and SQLite (per the PRD's "fully human-readable" invariant), and every write must update both in one operation.

These commands reuse the git-style vault discovery already built for `schema`. They also enforce the **structural field-set invariant**: every entity of a schema carries *exactly* that schema's user-defined field set (empty is fine; missing or extra fields are not), with `name`/`aliases` as built-in structural fields exempt from the schema.

- Write `forte entity` behavior spec
- Implement Entity domain model + markdown (frontmatter) serialization
- Implement Entity DB repository (dual-write markdown + SQLite)
- Implement entity service layer (add / list / show / edit / remove + validation)
- Wire `forte entity add` command and the `entity` group
- Wire `forte entity list` command
- Wire `forte entity show` command
- Wire `forte entity edit` command
- Wire `forte entity remove` command

---

Task: Write `forte entity` behavior spec
ACs:
- A new spec file `docs/spec/forte-entity.md` exists, following the structure of `docs/spec/forte-schema.md` (title + short intro paragraph, `## Scenarios` with Gherkin blocks, `## Out of scope`).
- Scenarios cover, at minimum:
  - `entity add <schema>` with a name and some field values succeeds in a valid vault: prints a success message including the assigned integer id, exits 0, creates `entities/<schema>/<slug>.md`, inserts a row in the `entities` table, and the entity is subsequently visible in `entity list` and `entity show <id>`.
  - `entity add` with **only a name** (no field values) succeeds: the entity carries every schema field back-filled to empty, plus `name`/`aliases`.
  - `entity add` for a schema that does **not** exist exits non-zero with a clear "unknown schema" error and creates nothing.
  - `entity add` that supplies a field **not** in the schema exits non-zero with a clear error and creates nothing (structural invariant: no extra fields).
  - `entity add` with a missing/empty `--name` exits non-zero (name is required and non-empty).
  - `entity add` with one or more `--alias` values stores them as the entity's aliases.
  - `entity list` on a vault with several entities prints one line per entity including its id, schema, and name; `entity list --schema <schema>` restricts output to that schema; `entity list --schema <unknown>` (a schema that doesn't exist) exits non-zero with a clear "unknown schema" error; an empty vault prints a friendly "no entities" message and exits 0.
  - `entity show <id>` prints the entity's id, schema, name, aliases, and each field with its value; showing a non-existent id exits non-zero with a clear error.
  - `entity edit <id>` can change the name, set field values (only schema-defined fields), and add/remove aliases; changes are reflected in both `entity show` and the on-disk markdown file; editing an unknown field exits non-zero and changes nothing; editing a non-existent id exits non-zero.
  - `entity remove <id>` removes the entity (markdown file + DB row); afterward it no longer appears in `entity list` and `entity show <id>` errors; removing a non-existent id exits non-zero.
  - Any `entity` subcommand run **outside a vault** (no `.forte/` found walking up) exits non-zero with the shared "Not inside a Forte vault" error and does nothing.
Implementation Notes:
- Specs are the source of truth per CLAUDE.md and drive the integration tests written in the command tasks. Write this first so the command tasks have concrete assertions.
- Keep scenarios black-box: observable CLI behavior (stdout, exit code, on-disk markdown, DB row state) — mirror `forte-schema.md`, not internal function calls.
- Put explicitly **out of scope**: `forte entity search` (deferred with embeddings); document-linking / mentions display in `entity show` (no `doc ingest` yet, so the "linked docs" section is empty for now — say so); schema-mutation cascade onto existing entities (belongs to future `schema add-field`/`remove-field`); reconciling hand-edits to markdown that bypass the CLI (design says drift is not auto-reconciled at MVP); inline `$EDITOR`-based editing if the `edit` task chooses the flag-based interface.
- Nail down the exact flag surface with the `entity add`/`edit` tasks and keep the spec consistent with it (see those tasks for the proposed `--name` / `--alias` / `--field name=value` / `--set` shapes).

Task: Implement Entity domain model + markdown (frontmatter) serialization
ACs:
- Domain layer: `src/forte/domain/entity.py` exports an `Entity` model with: `id: int | None` (None before it's been assigned by SQLite), `schema: str`, `name: str`, `aliases: list[str]`, `fields: dict[str, str]` (ordered to match the schema's field order), `body: str` (free-form markdown notes, empty by default), and `file_path: str | None`.
- A serialization module (recommended: `src/forte/domain/entity_markdown.py`, or a pair of functions on/near the model) provides:
  - `to_markdown(entity) -> str` — renders YAML frontmatter carrying the built-in `name` and `aliases` plus each schema field (in order), followed by the free-form body. Field values are strings; empty values render as empty (not omitted), preserving the structural field set on disk.
  - `from_markdown(text) -> ParsedEntity` — parses frontmatter + body back into name, aliases, fields dict, and body. (`id`/`schema`/`file_path` are not stored *in* the frontmatter; they come from the DB row / file location — decide and document this split.)
- Round-trip is stable: `from_markdown(to_markdown(e))` recovers name, aliases, fields (with order), and body.
- A small helper produces the entity's on-disk filename slug from its canonical name (lowercase, spaces→hyphens, strip unsafe chars) — reuse or share the slug logic already used for schema-name validation where it fits.
- Unit tests cover round-trip, empty-field rendering, empty-alias list, and slug generation for a few representative names.
Implementation Notes:
- **YAML dependency:** there is currently no YAML library in `pyproject.toml` (config.yaml is written as a plain comment today). Frontmatter is YAML per solution-design's "File conventions", so add `pyyaml` to `dependencies` and use `yaml.safe_load` / `yaml.safe_dump` for the frontmatter block. (Hand-rolling YAML is a trap once aliases/values contain colons, quotes, or unicode — use the library.) Flag this dependency addition in the PR.
- Frontmatter always carries `name` (required) and `aliases` (list, possibly empty) as **built-in structural fields**, then the user-defined schema fields. `name`/`aliases` are NOT schema-defined — keep them separate from the `fields` dict in the model (matches solution-design: "`name` and `aliases` are structural … *not* schema-defined fields").
- This is the domain layer — **pure, no filesystem or DB I/O.** `to_markdown`/`from_markdown` operate on strings; the repository (next task) owns reading/writing the actual files.
- The `entities` table columns are `(id, schema, name, aliases_json, fields_json, file_path)` — the model maps cleanly onto these. `aliases` and `fields` serialize to the `_json` columns in the repo; on disk they live in frontmatter. Keep the JSON (DB) and YAML (markdown) serializations distinct concerns.

Task: Implement Entity DB repository (dual-write markdown + SQLite)
ACs:
- DB layer: `src/forte/db/entity_repository.py` exposes a repository over an open vault (`root: Path`) providing:
  - `add(entity: Entity) -> Entity` — assigns the SQLite auto-increment id, writes the markdown file at `entities/<schema>/<slug>.md`, inserts the `entities` row (`schema`, `name`, `aliases_json`, `fields_json`, `file_path`), and returns the entity with its new `id` and `file_path` populated — markdown file and DB row created together.
  - `get(id: int) -> Entity | None` — single lookup by id, hydrating aliases/fields from the JSON columns.
  - `list(schema: str | None = None) -> list[Entity]` — all entities, or only those of `schema`, ordered by id.
  - `update(entity: Entity) -> None` — rewrites the markdown file and updates the row for an existing id. If the name (and therefore slug) changed, rename/rewrite the file and update `file_path` accordingly; do not leave the old file behind.
  - `remove(id: int) -> None` — deletes the markdown file and the `entities` row together.
- Dual-write ordering is consistent and leaves no half-state on the common path: the DB row and the markdown file agree on `file_path` after every operation.
- Integration tests against a temp vault (real SQLite + real files) assert: after `add`, the file exists at the expected path, its frontmatter matches, and the row is present with the returned id; `get`/`list` round-trip fields and aliases; `update` reflects in both file and row (including a rename when the name changes); after `remove`, both file and row are gone. `list(schema=...)` filters correctly.
- Filename collision is handled deterministically: if `<slug>.md` already exists for a *different* entity (two entities with the same name), disambiguate (e.g. append `-<id>`) rather than overwriting. Cover this with a test.
- Follow the existing repo style: stdlib `sqlite3`, one connection per operation, JSON via `json.dumps`/`loads` for the `_json` columns (see `db/schema_repository.py`).
Implementation Notes:
- The `entities(id, schema, name, aliases_json, fields_json, file_path)` table already exists from the `forte init` bootstrap (`src/forte/db/schema.py`) — read/write it, don't redefine it. `id` is `INTEGER PRIMARY KEY AUTOINCREMENT`; let SQLite assign it (`cursor.lastrowid`) rather than computing ids yourself.
- Derive paths via `VaultLayout(root).entities_dir / schema / f"{slug}.md"` — don't hardcode `entities/`. The `entities/<schema>/` folder is created when the schema is added (`SchemaRepository.add`), so it should already exist; still, fail loudly with a clear error if it's missing rather than silently `mkdir`-ing a folder for a schema that doesn't exist (that's the service layer's guard, but the repo shouldn't paper over it).
- `file_path` stored in the DB should be **vault-relative** (e.g. `entities/person/ben-sivongxay.md`), not absolute, so vaults stay portable. Be consistent with how any existing `file_path`-style values are stored.
- Unlike the schema repo (which uses `Path.rmdir` on an empty folder), entities are single files — remove with `Path.unlink`.
- Store aliases and fields as JSON in the DB (`aliases_json`, `fields_json`) and as YAML frontmatter on disk (via the serializer from the previous task). The repository is the single place both writes happen; keep the dual-write in one method so they can't drift within an operation.

Task: Implement entity service layer (add / list / show / edit / remove + validation)
ACs:
- `src/forte/services/entity.py` exposes `add_entity`, `list_entities`, `get_entity` (for `show`), `edit_entity`, and `remove_entity`, each taking the vault root and orchestrating validation + `SchemaRepository` + `EntityRepository`.
- `add_entity(root, schema, name, aliases, field_values)` enforces, before any write:
  - The `schema` exists (else typed "unknown schema" error) — look it up via `SchemaRepository`.
  - `name` is present and non-empty (built-in required field).
  - Every key in `field_values` is a field **declared by that schema** — any unknown field is a typed error (structural invariant: no extra fields).
  - Back-fills any schema field the caller omitted with an empty string, so the stored entity carries **exactly** the schema's field set (structural invariant: no missing fields).
  - Then calls the repository and returns the created `Entity` (with id).
- `list_entities(root, schema=None)` returns all entities, or those of a given schema; raises a typed "unknown schema" error if a filter names a schema that doesn't exist.
- `get_entity(root, id)` returns the entity or raises a typed "not found" error.
- `edit_entity(root, id, ...)` supports: changing `name`, setting values for **existing schema fields only** (unknown field → typed error, no write), and adding/removing aliases. Re-applies the structural invariant (the field set stays exactly the schema's) and delegates the dual-write (including any file rename on name change) to the repository. Editing a non-existent id raises "not found".
- `remove_entity(root, id)` raises "not found" if the id doesn't exist, else removes via the repository.
- Typed exceptions (e.g. `EntityNotFoundError`, `UnknownSchemaError`, `InvalidEntityError`) so the driver maps each to a `click.ClickException` — mirrors `services/schema.py`.
- Unit/integration tests cover each validation branch (unknown schema, missing name, unknown field on add and on edit, not-found on show/edit/remove) and the happy paths.
Implementation Notes:
- The structural field-set invariant is the core business rule here (solution-design "Schemas": "every entity of a schema must carry *exactly* that schema's field set"). Enforce it in the service, using the schema's field list as the source of truth — the domain/repo layers shouldn't have to know schema definitions.
- Field **values** are free-text strings, all optional; there is no per-field type or value validation at MVP. Only the *set of field names* is constrained.
- Keep all business logic here, not in the Click commands (driver layer is "no business logic"). The service reads the schema to validate and back-fill, then hands a fully-formed `Entity` to the repository.
- `entity search` is explicitly not part of this service — don't add it.
- Schema-mutation cascade (a schema gaining/losing a field, back-filling existing entities) is a separate future concern; this batch only guarantees the invariant holds at entity write time against the schema as it exists then.

Task: Wire `forte entity add` command and the `entity` group
ACs:
- `forte.cli` gains an `entity` Click **group** registered under the top-level `main` group, and an `add` subcommand: `forte entity add <schema> --name <name> [--alias <a> ...] [--field <k>=<v> ...]`.
- `<schema>` is a positional argument; `--name` is required; `--alias` is repeatable (`multiple=True`) → aliases list; `--field` is a repeatable `key=value` option (`multiple=True`) → field values (parse `k=v`, erroring clearly on malformed input with no `=`).
- Resolves the vault via `find_vault_root(Path.cwd())`, calls `services.entity.add_entity`, and on success prints a one-line confirmation including the assigned id (e.g. `Added person entity #4: Ben Sivongxay`) and exits 0.
- Outside a vault → non-zero exit with the shared discovery error. Service validation errors (unknown schema, missing/empty name, unknown field) → `click.ClickException`, non-zero exit, no partial writes.
- Integration test uses `CliRunner` + `isolated_filesystem()`: `forte init`, `forte schema add person --field employer --field role`, then `forte entity add person --name "Ben" --field employer=Acme` and asserts the entity is stored (visible via follow-up `entity list`/`entity show`, the markdown file exists, and the DB row is present).
- This task lands the `entity` group, so it must merge before the `list`/`show`/`edit`/`remove` command tasks (they attach to the same group).
Implementation Notes:
- Follow the driver pattern in `src/forte/cli/__init__.py`: thin command, `try/except` mapping the service's typed errors to `click.ClickException(str(e))`. Reuse the existing `find_vault_root` + `VaultNotFoundError` handling verbatim.
- `--field k=v` parsing: split on the first `=` only (values may contain `=`); a token with no `=` is a usage error. Consider a tiny helper so `edit`'s `--set` can reuse it.
- `cli/__init__.py` is growing (init + schema already there). Splitting per-group modules (e.g. `cli/entity.py` with the group registered onto `main`) is acceptable if done cleanly; matching the current single-file structure is also fine — pick one, be consistent, and note the schema tasks left this same choice open.
- Use `Path.cwd()` as the discovery start, consistent with `init` and `schema`.

Task: Wire `forte entity list` command
ACs:
- `forte entity list` prints one line per entity including its id, schema, and name; `--schema <schema>` filters to a single schema. On a vault with no matching entities it prints a friendly message (e.g. `No entities yet.`) and exits 0.
- Resolves the vault via discovery; outside a vault exits non-zero with the shared error.
- Output is stable enough to assert on (id, schema, and name appear per row).
- Integration test adds entities across two schemas, asserts all appear in `entity list`, and that `entity list --schema person` shows only the person entities. Plus an empty-vault message test.
Implementation Notes:
- Plain `click.echo` lines are fine (e.g. `#4  person  Ben Sivongxay`); a `rich.table.Table` is optional polish. Keep it test-friendly.
- If `--schema` names a schema that doesn't exist, exit non-zero with the service's "unknown schema" error (do NOT silently return an empty list) — this catches typos rather than masking them. Cover it with a test.
- Depends on the `entity` group existing (add-command task).

Task: Wire `forte entity show` command
ACs:
- `forte entity show <id>` prints the entity's id, schema, name, aliases, and each schema field with its (possibly empty) value, in schema field order. It also prints the free-form body/notes if present.
- Showing a non-existent id exits non-zero with a clear "not found" error.
- Resolves the vault via discovery; outside a vault exits non-zero.
- Integration test adds an entity with fields and aliases, then asserts `entity show <id>` output contains the name, each field name and value, and the aliases.
Implementation Notes:
- PRD describes `entity show` as "fields and linked docs". Linked docs (mentions) come from `doc ingest`, which doesn't exist yet, so **the linked-docs section is empty/omitted for this batch** — leave a clear seam (e.g. a "Mentions: (none)" line or just omit) but do not build mention querying now. Note this in the spec's out-of-scope.
- Read via `services.entity.get_entity`; map `EntityNotFoundError` to `click.ClickException`.
- `<id>` is an integer argument (`type=int`); a non-integer id should fail as a usage error naturally via Click.

Task: Wire `forte entity edit` command
ACs:
- `forte entity edit <id>` supports editing via flags: `--name <name>` (rename), `--set <k>=<v>` (repeatable; set a schema field's value), `--add-alias <a>` (repeatable), `--remove-alias <a>` (repeatable).
- Applies the changes through `services.entity.edit_entity`, dual-writing markdown + DB (including renaming the markdown file if the name/slug changed). On success prints a confirmation and exits 0.
- `--set` for a field not defined by the entity's schema exits non-zero with a clear error and changes nothing.
- Editing a non-existent id exits non-zero. Outside a vault exits non-zero.
- Integration test: add an entity, then `entity edit <id> --set role=Engineer --add-alias "Ben S."`, and assert the change is visible in `entity show` AND in the on-disk markdown file; a separate test asserts `--set unknown_field=x` errors and leaves the entity unchanged; a test asserts renaming updates the markdown filename and removes the old file.
Implementation Notes:
- Reuse the `k=v` parsing helper from `entity add` for `--set`.
- **Interface decision:** this batch uses a **flag-based** edit (deterministic and testable via `CliRunner`, and agent-friendly). Opening the markdown file in `$EDITOR` (`click.edit()`) and re-parsing via `from_markdown` is a natural richer alternative — note it as a future option in the spec's out-of-scope, but don't build it now.
- `--add-alias`/`--remove-alias` mutate the alias list additively/subtractively (removing a non-present alias is a no-op or a clear error — pick one, keep it consistent with the spec). This directly serves UJ2 ("adds the missing alias to the existing entity via `forte entity edit`").
- Depends on the `entity` group existing.

Task: Wire `forte entity remove` command
ACs:
- `forte entity remove <id>` removes the entity's markdown file and DB row; afterward it no longer appears in `entity list` and `entity show <id>` errors.
- Prompts for confirmation before removing (destructive), with a `--yes`/`-y` flag to skip the prompt for non-interactive/agent use — same convention as `schema remove`.
- Removing a non-existent id exits non-zero with a clear "not found" error and removes nothing. Outside a vault exits non-zero.
- Integration test: add an entity, `entity remove <id> --yes`, then assert both the markdown file and the DB row are gone and `entity show <id>` now errors; plus a test that removing an unknown id errors.
Implementation Notes:
- Use `click.confirm(...)` gated behind the absence of `--yes`, mirroring `schema_remove` in `cli/__init__.py` (reuse the exact flag name/pattern for consistency).
- Map `services.entity.EntityNotFoundError` to `click.ClickException`.
- Depends on the `entity` group existing.

# `forte schema` add/list/remove - Tasks

Feature: Implement the `forte schema` command group (`add`, `list`, `remove`) per PRD ("Schemas", UJ1 step 2) and solution-design.md ("Schemas", "CLI Spec", "SQLite Schema"). End state: a user in an existing vault can define a named entity kind and its free-text fields (`forte schema add person --field employer --field role`), list all defined schemas, and remove a schema. Schema definitions are stored in the SQLite `schemas` table and the matching `entities/<schema>/` folder is created/removed alongside them.

These are the first commands that operate on an *existing* vault (unlike `forte init`), so they introduce git-style vault discovery as shared infrastructure.

- Write `forte schema` behavior spec
- Implement vault discovery (git-style walk-up)
- Implement Schema domain model + DB repository
- Implement schema service layer (add / list / remove + validation)
- Wire `forte schema add` command and the `schema` group
- Wire `forte schema list` command
- Wire `forte schema remove` command

---

Task: Write `forte schema` behavior spec
ACs:
- A new spec file `docs/spec/forte-schema.md` exists, following the structure of `docs/spec/forte-init.md` (title, short intro, `## Scenarios` with Gherkin blocks, `## Out of scope`).
- Scenarios cover, at minimum:
  - `schema add <name>` with one or more `--field` flags succeeds in a valid vault: prints success, exits 0, and the schema is subsequently visible in `schema list`.
  - `schema add` with **no** `--field` flags succeeds (a schema may have zero user-defined fields; entities of it carry only the built-in `name`/`aliases`).
  - `schema add` for a name that already exists exits non-zero with a clear "already exists" error and does not modify the existing schema.
  - `schema add` rejects `name` or `aliases` as a field (reserved built-in structural fields), exits non-zero, nothing created.
  - `schema add` rejects duplicate `--field` values within one invocation.
  - `schema add` rejects an invalid schema name (not a folder-safe slug — e.g. contains spaces, slashes, uppercase) with a clear error.
  - `schema list` on a vault with several schemas prints each schema name and its fields; on an empty vault prints a friendly "no schemas defined" message and exits 0.
  - `schema remove <name>` removes an existing schema (row + `entities/<name>/` folder) and it no longer appears in `schema list`.
  - `schema remove` of a non-existent schema exits non-zero with a clear error.
  - Any `schema` subcommand run **outside a vault** (no `.forte/` found walking up) exits non-zero with a clear "not inside a Forte vault" error.
Implementation Notes:
- Specs are the source of truth per CLAUDE.md and drive the integration tests written in later tasks. Write this first so the command tasks have concrete assertions to satisfy.
- Keep scenarios black-box: describe observable CLI behavior (stdout, exit code, on-disk vault state), not internal function calls — mirror how `forte-init.md` is written.
- Put schema-mutation cascade behavior (back-fill / strip fields on existing entities) explicitly **out of scope** here — that belongs to the future `schema add-field` / `remove-field` commands, not to whole-schema add/remove. At MVP, `schema remove` of a schema that still has entities is covered by the service-layer task below (block with an error); reflect whatever that task decides in an out-of-scope or edge-case note.

Task: Implement vault discovery (git-style walk-up)
ACs:
- A new module (recommended: `src/forte/services/discovery.py`) exposes `find_vault_root(start: Path) -> Path` that walks upward from `start` and returns the first ancestor directory containing a `.forte/` directory.
- When no `.forte/` directory is found up to the filesystem root, it raises a clear, typed error (e.g. `VaultNotFoundError`) whose message tells the user they are not inside a Forte vault.
- Returns the vault **root** (the directory that contains `.forte/`), not the `.forte/` dir itself; callers build a `VaultLayout` from it.
- Unit tests cover: found in `start` itself, found in an ancestor several levels up, and not-found (raises).
Implementation Notes:
- Solution design specifies discovery is "git-style: each command walks up from CWD looking for a `.forte/` directory."
- This does filesystem I/O, so it must NOT live in `src/forte/domain/vault.py` (that module is documented as pure path arithmetic, no I/O). A service-layer module is the right home.
- Reuse `VaultLayout` for the `.forte/` path name rather than hardcoding the string a second time (e.g. check `VaultLayout(dir).forte_dir.is_dir()`), keeping the `.forte` constant in one place.
- Stop at the filesystem root; guard against an infinite loop by comparing `parent == current`.
- This is shared infrastructure — every non-`init` command (schema, entity, doc) will use it. Build it once here.

Task: Implement Schema domain model + DB repository
ACs:
- Domain layer: `src/forte/domain/schema.py` exports a small immutable `Schema` model (e.g. a frozen dataclass) with `name: str` and `fields: list[str]` (ordered). No I/O in the domain module.
- DB layer: `src/forte/db/schema_repository.py` (distinct from the existing `db/schema.py`, which is the DDL bootstrap) exposes a repository over an open vault that provides:
  - `add(schema: Schema) -> None` — inserts a row into the SQLite `schemas` table (`name`, `fields_json`) **and** creates the `entities/<name>/` folder, in one operation.
  - `list() -> list[Schema]` — returns all schemas, deserializing `fields_json`.
  - `get(name: str) -> Schema | None` — single lookup.
  - `remove(name: str) -> None` — deletes the `schemas` row **and** removes the `entities/<name>/` folder.
  - `exists(name: str) -> bool`.
- `fields` are serialized to/from the `fields_json` TEXT column as a JSON array, preserving order.
- Integration tests against a temp vault (real SQLite + real folders) assert: after `add`, the DB row exists and `entities/<name>/` is a directory; `list`/`get` round-trip the field order; after `remove`, the row is gone and the folder is gone.
Implementation Notes:
- The `schemas(name, fields_json)` table already exists from the `forte init` bootstrap (`src/forte/db/schema.py`) — do NOT redefine it; just read/write it.
- `name` is the primary key of `schemas`; the folder name under `entities/` is the same slug. Derive the folder path via `VaultLayout(root).entities_dir / name` — do not hardcode `entities/`.
- Dual-write ordering for `add`: create the DB row and the folder together; if the folder already exists unexpectedly, treat it as an error condition surfaced to the service layer rather than silently reusing it.
- For `remove`, only remove the `entities/<name>/` folder if it is empty of entity files. Guarding against deleting a folder that still holds entities is the service layer's job (next task); the repository can assume the caller has checked, but should still fail loudly (not `rmtree` blindly) — prefer `Path.rmdir()` which refuses a non-empty dir over `shutil.rmtree`.
- Follow the existing repo style: stdlib `sqlite3`, open a connection per operation (see `db/schema.py`), no ORM.
- Schemas are configuration/metadata, so the SQLite `schemas` table is their authoritative store; the `entities/<schema>/` folder is the browsable on-disk artifact. This is consistent with the design — the "fully human-readable" invariant in the PRD applies to docs and entities (the knowledge base), not to schema metadata. Do not invent an extra per-schema markdown/yaml file at MVP.

Task: Implement schema service layer (add / list / remove + validation)
ACs:
- `src/forte/services/schema.py` exposes `add_schema`, `list_schemas`, and `remove_schema` functions that take the vault root (resolved by the discovery task) and orchestrate validation + the repository.
- `add_schema(root, name, fields)` enforces, before any write:
  - `name` is a folder-safe slug (lowercase alphanumeric + hyphen/underscore, no spaces/slashes/uppercase); otherwise raise a typed validation error with a helpful message.
  - `name` does not already exist as a schema (else typed "already exists" error).
  - No field is named `name` or `aliases` (reserved built-in structural fields per solution design's "File conventions").
  - No duplicate field names within `fields`.
  - Zero fields is allowed.
- `list_schemas(root)` returns all schemas (ordered by name is fine).
- `remove_schema(root, name)`:
  - Raises a typed "not found" error if the schema does not exist.
  - Blocks removal with a clear error if any entities of that schema currently exist (query the `entities` table for rows with `schema = name`), instructing the user to remove those entities first. (Entity-creation commands don't exist yet, so this is forward-looking, but it prevents orphaning entities once they do.)
  - Otherwise removes via the repository.
- Unit/integration tests cover each validation branch (invalid slug, duplicate schema, reserved field, duplicate field) and the happy paths.
Implementation Notes:
- Define typed exceptions (e.g. `SchemaExistsError`, `SchemaNotFoundError`, `InvalidSchemaError`, `SchemaInUseError`) so the driver layer can map each to a `click.ClickException` with the right message — mirrors how `services/init.py` raises `VaultAlreadyExistsError` for `cli` to catch.
- Solution design: fields are free-text at MVP, all optional, no per-field types — so `fields` is just a `list[str]` of names. Do not build a type system.
- Keep business logic here, not in the Click command — the driver layer is documented as "no business logic".
- The slug rule is the same rule filenames use elsewhere ("Filenames are slugified from the canonical entity name"); a shared `slugify`/`is_valid_slug` helper is reasonable but not required for this task.

Task: Wire `forte schema add` command and the `schema` group
ACs:
- `forte.cli` gains a `schema` Click **group** registered under the top-level `main` group, and an `add` subcommand: `forte schema add <name> --field <f> --field <f> ...`.
- `--field` is a repeatable option collecting into a tuple/list (`multiple=True`); zero `--field` flags is valid.
- The command resolves the vault via the discovery service (walk up from `Path.cwd()`), then calls `services.schema.add_schema`. On success it prints a one-line confirmation (e.g. "Added schema 'person' with fields: employer, role") and exits 0.
- Outside a vault, it exits non-zero with the discovery error message.
- Validation errors from the service (already-exists, invalid slug, reserved/duplicate field) surface as `click.ClickException` with a non-zero exit and no partial writes.
- An integration test uses `CliRunner` + `isolated_filesystem()`, runs `forte init` then `forte schema add`, and asserts the schema is stored (visible via a follow-up `schema list` or by inspecting the DB/folder), matching the spec scenarios.
Implementation Notes:
- Follow the existing driver pattern in `src/forte/cli/__init__.py`: thin command, `try/except` mapping the service's typed errors to `click.ClickException(str(e))`.
- Registering the group: `@main.group()` for `schema`, then `@schema.command("add")`. The CLI file may be getting large — splitting `cli/__init__.py` into per-group modules (e.g. `cli/schema.py`) is acceptable if done cleanly, but keeping it in one file to match the current structure is also fine; pick one and be consistent.
- This task lands the `schema` group, so it must merge before the `list`/`remove` command tasks (they attach to the same group).
- Use `Path.cwd()` as the discovery start point, consistent with how `init` uses `Path.cwd()`.

Task: Wire `forte schema list` command
ACs:
- `forte schema list` prints every defined schema with its fields; on a vault with no schemas it prints a friendly message (e.g. "No schemas defined yet.") and exits 0.
- Resolves the vault via discovery; outside a vault exits non-zero with the discovery error.
- Output is readable and stable enough to assert on in tests (schema name and its field names appear).
- An integration test adds two schemas then asserts both names and their fields appear in `schema list` output, plus a test for the empty-vault message.
Implementation Notes:
- Rich is already in the stack (used for TUI prompts); a `rich.table.Table` gives clean output, but plain `click.echo` lines are perfectly acceptable at MVP. Keep it simple and test-friendly.
- Depends on the `schema` group existing (previous task).

Task: Wire `forte schema remove` command
ACs:
- `forte schema remove <name>` removes an existing schema and its `entities/<name>/` folder; afterward it no longer appears in `schema list`.
- Prompts for confirmation before removing (destructive), with a `--yes`/`-y` flag to skip the prompt for non-interactive/agent use.
- Removing a non-existent schema exits non-zero with a clear error.
- Removing a schema that still has entities exits non-zero with the service's "schema in use" error and removes nothing.
- Resolves the vault via discovery; outside a vault exits non-zero.
- An integration test adds a schema, removes it with `--yes`, and asserts it is gone from both the DB and the `entities/` folder; plus a test that removing an unknown schema errors.
Implementation Notes:
- Use `click.confirm(...)` (or Rich `Confirm.ask`) gated behind the absence of `--yes`; solution design establishes `--yes` as the convention for non-interactive approval (see `doc ingest --yes`), so reuse the same flag name here for consistency.
- Map the service's `SchemaNotFoundError` / `SchemaInUseError` to `click.ClickException`.
- Depends on the `schema` group existing (add-command task).

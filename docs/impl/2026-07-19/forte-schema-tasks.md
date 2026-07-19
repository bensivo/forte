# `forte schema add/list/remove` - Tasks

Feature: Implement the schema-definition commands per PRD ("Schemas") and solution-design.md ("Schemas", "SQLite Schema", "Vault Folder Structure"). End state: on an existing vault a user can define a named entity kind and its fields via `forte schema add <name> [--field ...]`, enumerate defined schemas via `forte schema list`, and drop one via `forte schema remove <name>`. Schema definitions live in the `schemas(name, fields_json)` SQLite table; each schema owns an `entities/<name>/` folder on disk.

Scope note: this feature covers the three whole-schema commands only. The per-field commands (`schema add-field` / `remove-field`) and the cascade-to-existing-entities behavior are explicitly follow-ups (solution-design.md), and entity commands do not exist yet — so there are no existing entities to migrate at this stage.

- Write the `forte schema` behavior spec
- Implement git-style vault discovery helper
- Define the `Schema` domain model and validation rules
- Implement the schema repository (SQLite + entity folder)
- Implement the schema service layer (orchestration + errors)
- Wire the `forte schema add/list/remove` Click commands

---

Task: Write the `forte schema` behavior spec
ACs:
- `docs/spec/forte-schema.md` exists and follows the same structure as `docs/spec/forte-init.md` (title, short intro, `## Scenarios` with Gherkin blocks, `## Out of scope`).
- Scenarios cover, at minimum: adding a schema with several `--field` flags; adding a schema with no fields; listing schemas when none exist and when several exist; adding a schema whose name already exists (error); adding a schema with a reserved field name `name` or `aliases` (error); adding a schema with a duplicate `--field` (error); removing an existing schema; removing a non-existent schema (error); running any `schema` subcommand outside a vault (error).
- Scenarios assert observable behavior only: stdout/stderr messages, exit codes, and resulting on-disk / DB state (the schema row exists/absent, the `entities/<name>/` folder created/removed). No internal function names.
- The "remove a schema that still has entities" case is captured as a scenario reflecting the chosen default from the repository/service tasks below (block with an error; do not delete entities).
Implementation Notes:
- Per CLAUDE.md, specs in `docs/spec/` are the source of truth that drive the automated test cases in the tasks below — write this first so the other tasks assert against it.
- Mirror the Gherkin voice already used in `forte-init.md` ("Given the current working directory... When the user runs... Then the process...").
- Keep "out of scope" honest: per-field mutation commands, cascading field changes to existing entities, and any schema markdown file on disk are all out of scope here.

Task: Implement git-style vault discovery helper
ACs:
- A new function discovers the current vault by walking up from a starting directory to find the nearest ancestor containing a `.forte/` directory, returning a `VaultLayout` rooted there (or raising a clear, typed error when no vault is found).
- Suggested home: `src/forte/services/vault.py` exposing `find_vault(start: Path) -> VaultLayout` and a `VaultNotFoundError`. (Service layer, because it performs filesystem stat calls — the `VaultLayout` domain model stays pure.)
- Walking stops at the filesystem root; if no `.forte/` is found anywhere up the chain, `VaultNotFoundError` is raised with a message telling the user they are not inside a Forte vault.
- A pytest test builds a temp vault, `cd`s (or passes a start path) into a nested subdirectory, and asserts `find_vault` returns a `VaultLayout` whose `root` is the vault root; a second test asserts `VaultNotFoundError` is raised when starting outside any vault.
Implementation Notes:
- Solution-design.md specifies vault discovery is git-style: "each command walks up from CWD looking for a `.forte/` directory." This helper is the single implementation of that rule; every non-`init` command will use it.
- Reuse `VaultLayout` from `src/forte/domain/vault.py` for the return type so callers get all the well-known paths (`db_path`, `entities_dir`, etc.) for free.
- This is foundational and not schema-specific — it lands here because `forte schema` is the first command that operates on an already-initialized vault.

Task: Define the `Schema` domain model and validation rules
ACs:
- `src/forte/domain/schema.py` (domain layer, no I/O) exports a `Schema` model carrying a `name: str` and an ordered `fields: list[str]`.
- A validation entry point (e.g. a constructor/classmethod or `validate()`) enforces: `name` is a non-empty, safe single path segment (lowercase letters, digits, and hyphens — usable as an `entities/<name>/` folder); `fields` contains no duplicates; no field equals the reserved built-in names `name` or `aliases`; each field name is non-empty. Empty `fields` (a schema with only the built-in `name`/`aliases`) is valid.
- Validation failures raise a clear, typed domain error (e.g. `InvalidSchemaError`) with a message naming the offending value; they do not raise bare `ValueError` with an opaque message.
- Helpers to serialize/deserialize the ordered field list to/from the JSON stored in `schemas.fields_json` (order preserved) live here or are trivially derivable.
- Unit tests cover: a valid schema round-trips through serialization; each validation rule rejects its bad input (bad name chars, empty name, duplicate field, reserved `name`/`aliases` field).
Implementation Notes:
- solution-design.md "Schemas": fields are free-text names with no per-field types or value validation at MVP — do NOT model field types, defaults, or required flags. A schema is just "a named entity kind plus an ordered list of field names."
- `name` and `aliases` are structural built-ins present on every entity regardless of schema and are NOT schema-defined — hence rejecting them as field names here.
- Preserve field order: `schemas.fields_json` is an ordered JSON array; do not sort or dedupe-reorder.
- Keep this layer pure (no filesystem, no sqlite) so it mirrors `domain/vault.py`.

Task: Implement the schema repository (SQLite + entity folder)
ACs:
- A db-layer module (e.g. `src/forte/db/schemas.py`) exposes CRUD over the `schemas` table plus the matching `entities/<name>/` folder, given a `VaultLayout` (or explicit db path + entities dir): `add_schema(Schema)`, `list_schemas() -> list[Schema]`, `get_schema(name) -> Schema | None`, `remove_schema(name)`.
- `add_schema` inserts a row into `schemas(name, fields_json)` and creates the `entities/<name>/` directory. If a schema of that name already exists, it raises a clear, typed error and writes nothing (no row, no folder side effects).
- `list_schemas` returns all schemas as `Schema` domain objects with field order preserved; returns an empty list when none are defined.
- `remove_schema` deletes the `schemas` row and removes the `entities/<name>/` folder. Chosen MVP default: if that folder contains any entity files, it raises a clear "schema still has entities" error and removes nothing; otherwise it deletes the (empty) folder and the row. Removing a name that does not exist raises a clear "no such schema" error.
- Integration tests against a real temp vault DB cover: add then list round-trips (including field order); duplicate-add raises; remove deletes both row and empty folder; remove of a missing schema raises; remove of a schema whose folder is non-empty raises and leaves the row intact.
Implementation Notes:
- solution-design.md "SQLite Schema": the table is `schemas(name, fields_json)` with `name` as PRIMARY KEY — the DDL already exists in `src/forte/db/schema.py` from the `init` work; this task only reads/writes it, no new tables.
- Follow the dual-write principle from solution-design.md ("Every markdown write goes through the DB layer"): the SQLite row and the on-disk `entities/<name>/` folder are the two representations of a schema and must be kept in sync in one operation. Note there is intentionally NO schema markdown file — schemas are defined by the DB row plus their folder, per the vault layout (which has no `schemas/` directory).
- Use the stdlib `sqlite3` module and connect to `layout.db_path`, consistent with `db/schema.py`.
- The "block remove when entities exist" default is chosen because entity deletion is a separate, destructive concern and no `entity remove` flow exists yet; cascade-delete is the noted alternative if the design later prefers it. Keep the check simple (folder contains no `*.md` entity files).

Task: Implement the schema service layer (orchestration + errors)
ACs:
- A service-layer module (e.g. `src/forte/services/schema.py`) exposes `add_schema(root, name, fields)`, `list_schemas(root)`, and `remove_schema(root, name)` that orchestrate: discover the vault (`find_vault`), build/validate a `Schema` domain object, and call the repository.
- Domain validation errors, "schema already exists", "no such schema", "schema still has entities", and "not inside a vault" all surface as clear, typed exceptions (or a small shared error hierarchy) that the driver layer can turn into user-facing messages — no raw sqlite or filesystem exceptions leak out.
- Integration tests drive these service functions against a real temp vault and assert both the return values and the resulting DB + folder state, plus that each error condition raises the expected typed error.
Implementation Notes:
- This mirrors `services/init.py`, which composes `VaultLayout` + `write_default_config` + `initialize_database` and raises a typed `VaultAlreadyExistsError` for the driver to catch.
- Keep orchestration here and business rules in the domain/repository layers — the service just wires them together and maps lower-level errors to a consistent surface.
- `add_schema` should validate via the domain model BEFORE touching the repository, so an invalid name/field never causes a partial write.

Task: Wire the `forte schema add/list/remove` Click commands
ACs:
- `forte schema` is a Click sub-group of the top-level `main` group, with `add`, `list`, and `remove` subcommands, registered in `src/forte/cli`.
- `forte schema add <name> --field <f1> --field <f2> ...` creates the schema: `--field` is a repeatable option (`multiple=True`) whose order is preserved; the command prints a one-line success message and exits 0. `--field` may be omitted entirely (zero-field schema).
- `forte schema list` prints each schema's name and its fields in a readable form (e.g. one line per schema); prints a friendly "no schemas defined" message when empty; exits 0.
- `forte schema remove <name>` removes the schema and prints a one-line confirmation; exits 0.
- Every error path (not in a vault, duplicate add, invalid name/field, reserved field, removing a missing schema, removing a schema that still has entities) exits non-zero with a clear message and no partial writes — implemented by catching the service-layer typed errors and re-raising as `click.ClickException`.
- `uv run forte schema --help` lists `add`, `list`, and `remove`; the base `forte --help` lists `schema` alongside `init`.
- pytest integration tests use Click's `CliRunner` with `isolated_filesystem()`: run `forte init`, then exercise add/list/remove end to end and assert on output, exit codes, and on-disk/DB state, matching the scenarios in `docs/spec/forte-schema.md`.
Implementation Notes:
- Keep the command file thin (driver layer), exactly like the existing `init` command: call into `services/schema.py` and translate typed service errors into `click.ClickException` (which yields a clean non-zero exit and stderr message).
- Use `@click.option("--field", "fields", multiple=True)` for repeatable fields; solution-design.md shows the intended UX: `forte schema add role --field company --field title`.
- Register the group with `main.add_command(...)` (or `@main.group()`); the base-CLI help already enumerates subcommands via the existing group, so `schema` will appear once registered — extend `docs/spec/cli-base.md` only if you want to assert its presence there.
- `list` is a Python builtin; name the Click callback something else (e.g. `list_schemas`) and set the command name explicitly (`@schema.command("list")`).

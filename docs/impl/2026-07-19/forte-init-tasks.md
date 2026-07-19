# `forte init` - Tasks

Feature: Implement the `forte init` command per PRD (UJ1, "Init, config, and vaults") and solution-design.md ("Vault Folder Structure", "SQLite Schema", "Configuration"). End state: `forte init` in an empty directory produces a valid vault with `.forte/index.db`, `.forte/config.yaml`, and the `docs/raw/`, `docs/processed/`, `entities/` folders.

- Define vault layout module
- Implement SQLite schema bootstrap
- Implement default config.yaml writer
- Wire `forte init` Click command
- Replace bare `forte` hello-world with help output

---

Task: Define vault layout module
ACs:
- `src/forte/domain/vault.py` (domain layer) exports a `VaultLayout` dataclass (or equivalent) that, given a root `Path`, exposes attribute paths for every well-known location: `forte_dir` (`.forte/`), `config_path` (`.forte/config.yaml`), `db_path` (`.forte/index.db`), `docs_raw_dir`, `docs_processed_dir`, `entities_dir`.
- A `VaultLayout.all_dirs()` (or equivalent) returns the ordered list of directories that `init` must create.
- No I/O happens in this module — it is pure path arithmetic. No `mkdir`, no `open`.
Implementation Notes:
- Solution design specifies the exact folder layout under "Vault Folder Structure": `.forte/`, `docs/raw/`, `docs/processed/`, `entities/`.
- Keeping this in the domain layer means the service and driver layers can both reference the same layout without duplicating string constants.
- The per-schema subfolders under `entities/` (`entities/person/`, etc.) are created lazily when schemas are added — `init` does NOT create them.

Task: Implement SQLite schema bootstrap
ACs:
- `src/forte/db/schema.py` (db layer) exposes `initialize_database(db_path: Path) -> None` that creates a new SQLite file at `db_path` with all MVP tables from solution-design.md's "SQLite Schema (draft)" section: `documents`, `schemas`, `entities`, `entity_field_values`, `mentions`, `ingest_changes`.
- Calling `initialize_database` on a path where the file already exists raises a clear error (do not silently overwrite).
- The `entity_embeddings` table is deferred (embeddings decision open); do NOT create it in this task. Leave a one-line comment noting it is deferred.
- A pytest integration test creates a temp dir, calls `initialize_database`, connects to the resulting file, and asserts every expected table exists via `sqlite_master`.
Implementation Notes:
- Use the stdlib `sqlite3` module — solution design's tech stack calls this out explicitly.
- Column types can follow the schema draft literally: `documents(id INTEGER PRIMARY KEY AUTOINCREMENT, source_path TEXT, content_hash TEXT, raw_path TEXT, processed_path TEXT, ingested_at TEXT, status TEXT)` and so on. Use `INTEGER PRIMARY KEY AUTOINCREMENT` for `id` columns — solution design specifies auto-increment integer IDs.
- `aliases_json` and `fields_json` are `TEXT` (JSON serialized). `payload_json` too.
- Keep the DDL as a list of `CREATE TABLE` statements executed in a single transaction. Do not add indices at MVP unless a query obviously needs one.
- Do NOT run any migrations framework (Alembic etc.); a single fresh-init DDL is enough for MVP.

Task: Implement default config.yaml writer
ACs:
- `src/forte/services/config.py` (service layer) exposes `write_default_config(path: Path) -> None` that writes a placeholder `config.yaml` containing only a comment (e.g. `# Forte vault config — settings will be added here as features need them.`) and no keys.
- Calling `write_default_config` when the file already exists raises a clear error.
- A pytest test writes the config to a temp path and asserts the file exists and is non-empty.
Implementation Notes:
- Do NOT add `pyyaml` as a dependency yet — writing a comment-only file needs no YAML library. Add it when the first real config key is introduced.
- Solution design lists a `model:` / `api_keys:` shape as the eventual target, but per current guidance we don't populate any keys until a feature actually reads one. This keeps the file honest — no dead config.
- Later tasks (LLM client, model selection) will replace the placeholder with real keys and pull in `pyyaml` at that point.

Task: Wire `forte init` Click command
ACs:
- `uv run forte init` in an empty directory creates the full vault: `.forte/config.yaml`, `.forte/index.db`, `docs/raw/`, `docs/processed/`, `entities/`. Exits 0 and prints a one-line success message ("Initialized Forte vault in <abs path>").
- Running `forte init` in a directory that already contains a `.forte/` folder exits non-zero with a clear error message ("Forte vault already exists at <path>"). No files are modified.
- Running `forte init` in a non-empty directory (that lacks `.forte/`) succeeds — the vault can be initialized alongside pre-existing files.
- The command is a Click subcommand of the top-level `main` group (`forte.cli`).
- A pytest integration test uses `CliRunner` with `isolated_filesystem()` to run `forte init`, then asserts the layout exists and the DB has the expected tables.
Implementation Notes:
- Compose the three prior tasks: build a `VaultLayout` for `Path.cwd()`, `mkdir(parents=True)` each dir from `layout.all_dirs()`, then call `write_default_config` and `initialize_database`.
- Order of operations: check "already initialized" FIRST (return early with error before any writes). Then create dirs, then config, then DB. If DB init fails, do not attempt to roll back — MVP treats corruption as system failure per PRD non-functional requirements.
- Keep the command file thin (driver layer): it should orchestrate calls into services/db/domain but hold no business logic itself.

Task: Replace bare `forte` hello-world with help output
ACs:
- Running `uv run forte` with no subcommand prints the same help text as `uv run forte --help` and exits 0 (or Click's conventional exit code for a no-subcommand invocation — either is acceptable as long as it's not an error state that CI would flag).
- The `hello-world` string no longer appears anywhere in `src/forte/`.
- `docs/spec/cli-hello-world.md` is either updated to reflect the new behavior (rename to `docs/spec/cli-base.md` if appropriate) or removed.
- `tests/test_cli_smoke.py` is updated to assert on the new behavior (e.g. that `--help`-style usage text appears in output) or removed if fully superseded by the `forte init` test.
Implementation Notes:
- In Click, the standard pattern is either `invoke_without_command=True` with a callback that calls `click.echo(ctx.get_help())` when `ctx.invoked_subcommand is None`, or dropping `invoke_without_command` entirely and letting Click's default "missing command" behavior handle it. The former gives a cleaner UX (exit 0, no "Error: Missing command" prefix) — prefer it.
- This task depends on the `forte init` task landing first, so there is at least one real subcommand to route to.

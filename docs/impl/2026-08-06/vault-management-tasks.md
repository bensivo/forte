# docs/impl/2026-08-06/vault-management-tasks.md

Feature: new vault management — vaults live anywhere on disk, are registered in a user-level
registry at `~/.forte/`, and every other command operates on the default vault (or `--vault <name>`)
instead of walking up from the current directory. Source: `docs/input/2025-08-06 new-vault-functionality.md`.

- Redefine the vault layout model (`forte.db` / `forte.yaml`, no `.forte/`)
- Build the user-level vault registry (interface + `~/.forte/` client)
- Build `VaultService` (create / list / get / remove / set-default / resolve)
- Add vault selection plumbing so DB clients target a resolved vault root
- Add the `forte vault` CLI command group (`CliVaultController`)
- Add `--vault` to schema / entity / doc commands and retire cwd-based discovery
- Update specs and design docs for the new vault model

---

Task: Redefine the vault layout model (`forte.db` / `forte.yaml`, no `.forte/`)
ACs:
- `model/vault.py`'s `VaultLayout` no longer has a `forte_dir` property. `db_path` is `<root>/forte.db` and `config_path` is `<root>/forte.yaml`.
- `docs_dir`, `docs_raw_dir`, `docs_processed_dir`, `docs_staging_dir`, and `entities_dir` are unchanged, and `all_dirs()` returns the same set minus `forte_dir`.
- A `Vault` model exists in `model/vault.py` holding at least `name: str` and `path: Path` — this is the abstract type `VaultService` and the registry pass around. `VaultLayout` stays pure path arithmetic with no I/O.
- `model/vault.py` defines a `VaultError` base class plus subclasses covering: vault name already registered, vault name not found, no default vault set, target directory conflicts with an existing vault/folders, invalid vault name. The existing `VaultAlreadyExistsError` folds into this set; `VaultNotFoundError` moves here from `services/discovery.py`.
- Everything that reads `.forte/` paths (`client/fs_vault_fs.py`, `client/sqlite_*_db.py`, `service/init_service.py`, `services/config.py`) still passes its tests against the new layout.
Implementation Notes:
- Per the style guide, exceptions live in the `model/` module for the feature, one base class + subclasses, each subclass docstring stating the single condition that raises it.
- There is a duplicate legacy `domain/vault.py` with the old `.forte/` layout. Leave it alone in this task (it belongs to the legacy `services/`/`db/`/`cli/` stack); it gets deleted by the entrypoint-migration task. Do NOT try to make both layouts work at once.
- No backwards compatibility or migration for existing `.forte/` vaults — the tool is pre-release and this is a clean break. Say so plainly in the `VaultLayout` docstring so a future reader doesn't go looking for migration code.
- Vault names are user-facing registry keys: validate them with the same slug rule `SchemaService` uses (`^[a-z0-9][a-z0-9_-]*$`, see `_SLUG_RE` in `service/schema_service.py`) so `forte vault create My Vault!` fails cleanly rather than producing an unusable key.

Task: Build the user-level vault registry (interface + `~/.forte/` client)
ACs:
- `interface/vault_registry.py` defines `IVaultRegistry` with storage-only methods, ordered per the style guide (existence check first, then CRUD, then extras): `check_exists(name)`, `add(vault)`, `get(name)`, `list()`, `remove(name)`, `get_default()`, `set_default(name)`.
- `client/yaml_vault_registry.py` implements it against a user-level config file at `~/.forte/config.yaml`, creating `~/.forte/` on first write.
- The file format is human-readable YAML, e.g. `default: personal` plus a `vaults:` mapping of name → absolute path. Reading a missing or empty file yields "no vaults, no default" rather than raising.
- The registry stores absolute, resolved paths — a vault registered as `.` from `/Users/x/notes` records `/Users/x/notes`.
- The interface raises no feature errors and does no validation (per style guide); it returns `None` for missing lookups and lets `VaultService` decide what's an error.
- The home directory location is injectable (constructor arg defaulting to `Path.home()`) so tests can point it at a tmp dir. Unit tests cover: empty/missing file, add + get round trip, list ordering, remove, default get/set, and that a removed default clears or is reported as unset.
Implementation Notes:
- This is a new user-level concern, distinct from the per-vault `forte.yaml` handled by `services/config.py`. Don't merge the two readers — per-vault config holds model/API-key settings, the registry holds "which vaults exist".
- Use `yaml.safe_load` / `yaml.safe_dump`, consistent with `services/config.py`. Write the whole file on each mutation; no partial-file editing needed at this scale.
- Deciding what happens when the default vault is removed is a service-layer call, not the registry's — see the `VaultService` task.

Task: Build `VaultService` (create / list / get / remove / set-default / resolve)
ACs:
- `service/vault_service.py` defines `VaultService`, constructor-injected with `IVaultRegistry` and `IVaultFs`, exposing: `create_vault(name, path) -> Vault`, `list_vaults() -> list[Vault]`, `get_vault(name) -> Vault`, `remove_vault(name)`, `set_default_vault(name)`, and a resolution method `resolve_vault(name: str | None) -> Vault`.
- `create_vault` validates first, writes second (style guide: no partial writes) — validate the name slug, that the name isn't already registered, and that the target has no conflicting `forte.db` / `forte.yaml` / `docs/` / `entities/`; only then create directories, write `forte.yaml`, initialize `forte.db`, and register the vault.
- If `create_vault` succeeds and no default is currently set, the new vault becomes the default. First-run `forte vault create personal .` therefore leaves a usable default with no extra command.
- `resolve_vault(None)` returns the default vault, raising the "no default vault set" error with a message telling the user to run `forte vault create` or `forte vault set-default`. `resolve_vault("name")` returns that vault or raises the not-found error. There is no walk-up-from-cwd fallback.
- `remove_vault` unregisters only — it never deletes files on disk. Removing the current default clears the default (rather than silently leaving a dangling name); this behavior is documented in the method docstring.
- Every method that can raise documents each exception type and its trigger condition in a `Raises:` section.
- Unit tests call `VaultService` directly as a controller would, against mock/fake `IVaultRegistry` and `IVaultFs`, covering the happy paths plus each raised error and the "no writes happened when validation failed" case.
Implementation Notes:
- `InitService` (`service/init_service.py`) becomes redundant once `create_vault` exists — its `init_vault` logic moves in, adjusted for the new layout, and `InitService` + `CliInitController` are deleted by the `--vault` migration task. Don't have `VaultService` call `InitService`; port the logic.
- `IVaultFs` already covers `exists` / `make_dirs` / `write_default_config` / `init_db`, which is exactly what `create_vault` needs — reuse it rather than adding a second filesystem interface.
- Depends on the layout-model and registry tasks.

Task: Add vault selection plumbing so DB clients target a resolved vault root
ACs:
- The four SQLite clients (`sqlite_schema_db`, `sqlite_entity_db`, `sqlite_document_db`, `sqlite_mention_db`) no longer call `find_vault_root(Path.cwd())`. Each resolves its `VaultLayout` from an injected, mutable `VaultContext` object holding the active vault root.
- `VaultContext` lives in `model/vault.py`: a small class with a `root: Path | None` attribute (or equivalent), a setter, and a getter that raises a typed error if no vault has been selected yet.
- `main.py` constructs one `VaultContext`, injects it into all four clients at wiring time, and the CLI sets it exactly once per invocation from the resolved vault (see the `--vault` task).
- Existing client behavior is otherwise unchanged; their tests are updated to inject a context pointed at a tmp vault instead of relying on cwd.
Implementation Notes:
- Layering matters here: clients must not import `VaultService` (clients never call services). `VaultContext` is a plain model object, which is why it goes in `model/` — that keeps the dependency direction legal while still letting a CLI-time decision reach the clients.
- The obvious alternative — threading a `vault_root: Path` parameter through every service and interface method — was considered and rejected: it changes every signature in `interface/` for a value that is constant for the lifetime of a process. If you find `VaultContext` leaking into business logic (services reading it directly), that's a smell; only clients should touch it.
- Keep the "resolve lazily, on each call" property the clients have today. They're constructed unconditionally at wiring time, before the vault is known, so nothing may read the context in `__init__`.
- Depends on the layout-model task. Can be built in parallel with `VaultService`.

Task: Add the `forte vault` CLI command group (`CliVaultController`)
ACs:
- `controller/cli_vault_controller.py` defines `CliVaultController`, constructor-injected with `VaultService`, exposing a `group()` method that builds the `vault` Click group, following `CliSchemaController`'s shape exactly (nested Click callbacks unpack args and delegate to private `_`-prefixed methods; all echoing and error handling in the private methods).
- Commands: `forte vault create <name> <path>`, `forte vault list`, `forte vault show <name>`, `forte vault remove <name>`, `forte vault set-default <name>`.
- `forte vault create personal .` creates the vault at the resolved absolute path and registers it, printing the vault name and absolute path. It works from any cwd.
- `forte vault list` prints each registered vault's name and path, marking the default (e.g. a `*` or `(default)` suffix), and prints a friendly "no vaults yet" line when the registry is empty.
- `forte vault show <name>` prints the vault's name, absolute path, and whether it's the default.
- `forte vault remove <name>` confirms before removing (with a `--yes` / `-y` flag to skip, matching `schema remove`) and its help text states plainly that it only unregisters the vault and does not delete files on disk.
- Every service call is wrapped in `try/except VaultError` and re-raised as `click.ClickException(str(e))` — the feature's base error class only, no catching of individual subclasses.
- Wired into `main.py` alongside the existing groups.
- Controller unit tests use Click's `CliRunner` against a mock `VaultService`, covering each command's output and the error-to-`ClickException` mapping.
Implementation Notes:
- The source doc is internally inconsistent: its "New behavior" section says `forte vault create <name> .` and `forte vault set-default <name>`, while its implementation checklist lists `forte vault add`. Resolved in favor of `create` (it matches `VaultService.create_vault` and the user-facing flow described first) plus `set-default`, which the checklist omits but the behavior section requires. If the user wanted `add` as the verb, this is the one-line change.
- No `forte vault edit` command at this stage — explicitly out of scope per the source doc.
- Depends on `VaultService`.

Task: Add `--vault` to schema / entity / doc commands and retire cwd-based discovery
ACs:
- `schema`, `entity`, and `doc` commands all accept a `--vault <name>` option. A single, consistently-placed option is used across all three groups (decide group-level vs command-level once and apply it uniformly; document the choice).
- On each invocation the controller resolves the vault via `VaultService.resolve_vault(vault_name)` and sets the `VaultContext` before calling its service. With no `--vault`, the default vault is used regardless of cwd.
- Running any of these commands with no default vault set and no `--vault` produces a clear `ClickException` telling the user to create or select a vault — not a traceback and not a "not inside a Forte vault" message.
- `forte init` and its `CliInitController` / `InitService` are removed; `forte vault create` fully replaces them. `services/discovery.py` and its `find_vault_root` are deleted, and no module in `service/`, `client/`, or `controller/` imports them (`grep -rn "find_vault_root\|services.discovery" src/` returns only legacy `cli/` hits, if any remain).
- Controllers catch `VaultError` alongside their own feature base error (e.g. `except (SchemaError, VaultError)`), replacing the current `VaultNotFoundError` catches.
- Existing behavior of every schema/entity/doc command is otherwise unchanged; their test suites pass with vault resolution stubbed or pointed at a tmp vault.
Implementation Notes:
- This is the task that actually delivers "commands work from anywhere". Sequence it after the plumbing and `VaultService` tasks.
- Where to resolve is a real design call: doing it in a top-level `main` group callback (`@click.option("--vault")` on `main`) gives one implementation but forces `forte --vault x doc list` ordering; doing it per-command gives the more natural `forte doc list --vault x` at the cost of repetition. Recommend per-group (`@click.group()` on `doc`/`schema`/`entity` taking `--vault`), which keeps `forte doc --vault x list` readable and localizes the change. Whichever you pick, apply it to all three groups identically and note it in each controller's class docstring.
- The controller resolving the vault and setting `VaultContext` is a thin wiring act, not business logic — resolution itself stays in `VaultService`. Keep the controller's part to a single call plus the context set.
- `forte init` disappearing is a user-visible breaking change; make sure `docs/spec/forte-init.md` is handled by the docs task rather than left describing a command that no longer exists.

Task: Update specs and design docs for the new vault model
ACs:
- New `docs/spec/forte-vault.md` covers, in the existing Gherkin style: creating a vault in an empty dir, creating one in a dir with conflicting `docs/`/`entities/`/`forte.db`, duplicate vault name, first vault becoming the default automatically, `list` with and without vaults, `show` for known and unknown names, `remove` (including removing the default, and confirming files stay on disk), and `set-default` for known and unknown names.
- `docs/spec/forte-init.md` is deleted or rewritten, since `forte init` no longer exists.
- `docs/spec/cli-base.md`, `forte-schema.md`, `forte-doc.md`, `forte-entity.md`, and `forte-agent*.md` are updated wherever they assume cwd-based vault discovery or `.forte/`, and gain scenarios for `--vault <name>` and for "no default vault set".
- `docs/solution-design.md` sections on vault folder structure (`.forte/index.db`, `.forte/config.yaml`), the CLI command table, and "Vault discovery is git-style" are updated to the new layout, the `~/.forte/config.yaml` registry, and the default-vault resolution order.
- `docs/prd.md`'s "Init, config, and vaults" requirements (lines describing `forte init`, git-style discovery, and `.forte/config.yaml`) are rewritten to match.
- `docs/index.md` needs no change unless a new top-level doc was added.
Implementation Notes:
- Specs are the source of truth for behavior in this project, so write the `forte-vault.md` scenarios before or alongside the CLI implementation, not after — they're the acceptance criteria the CLI task is really being measured against.
- Keep the existing spec file structure: a short intro, `## Scenarios` with `### Scenario:` subsections and gherkin fences, and an `## Out of scope` section at the end. `forte vault edit` and migrating pre-existing `.forte/` vaults both belong in "Out of scope".

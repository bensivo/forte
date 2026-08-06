# docs/impl/2026-08-05/service-refactor-tasks.md

NOTE: we never did all of these, just refactoring document, entity, and linking services. Teh vault stuff we went a different direection

- Refactor document service into 3-layer style
- Refactor entity service into 3-layer style
- Refactor linking into entity service
- Build user-level vault registry (config dir + interface/client)
- Refactor discovery into VaultService, backed by vault registry
- Add `forte vault` CLI commands (create, list, set-default, remove)
- Wire everything into main.py, retire legacy services/db/domain/cli folders

Task: Refactor document service into 3-layer style
ACs:
- New `service/document_service.py` defines `DocumentService` as a class, constructor-injected with whatever interfaces it needs (see below), with class + method docstrings matching schema_service.py's format.
- All business logic currently in `services/document.py` (ingest, list, get, link, unlink, remove) is preserved, including the "re-ingest is a no-op" and "link/unlink on already-linked/unlinked pair is a no-op" behaviors.
- `DocumentRepository`, `EntityRepository`, and `MentionRepository` (currently in `db/`) are replaced by interfaces defined in `interface/` (e.g. `IDocumentStore`, `IMentionStore`) with concrete implementations in `client/` (e.g. `SqliteDocumentStore`). `DocumentService` depends only on the interfaces, injected via constructor — it must not import from `db/`.
- `Document` model moves from `domain/document.py` to `model/document.py` (keep `compute_content_hash` alongside it, or move it into the client if it's really a storage-layer concern — use judgement, note the call either way).
- Typed exceptions (`DocumentError`, `DocumentNotFoundError`, `SourceFileNotFoundError`, `EntityNotFoundError`) move into `model/document.py`, matching schema_service's pattern of exceptions living in the model module.
- Old `services/document.py` and `db/document_repository.py` (and any now-unused parts of `db/mention_repository.py`) are deleted once callers are migrated — no dead duplicate code left behind.
- Unit tests exist for `DocumentService`, using mock/fake implementations of the new interfaces, calling functions directly as if it were the controller (per style guide).
Implementation Notes:
- Follow the shape of `service/schema_service.py` / `service/init_service.py` exactly: class + injected interface(s), google-style docstrings, custom exceptions raised before any write.
- `entity_exists`-type checks (document service currently reaches into `EntityRepository` to validate `entity_id` on link/unlink) should go through whatever interface the entity refactor task ends up defining — coordinate field naming with that task so `DocumentService` doesn't end up depending on entity-service internals, just a narrow "does entity X exist" interface method.
- Per docs/spec/forte-doc.md, don't change any observable behavior in this task — this is a structural refactor only.
- Text extraction (`services/text_extraction.py`) is out of scope for this task; leave it where it is or note as a fast-follow if it clearly belongs in `service/` too.

Task: Refactor entity service into 3-layer style
ACs:
- New `service/entity_service.py` defines `EntityService` as a class, constructor-injected with an `ISchemaStore` and an `IEntityStore` (or similar), matching schema_service.py's format for docstrings and structure.
- All business logic currently in `services/entity.py` is preserved: the structural field-set invariant (exact field set, in schema order, back-filled with `""`), name validation, unknown-field validation, alias add/remove semantics on edit.
- `EntityRepository` and `SchemaRepository` (in `db/`) become `IEntityStore` / `ISchemaStore` interfaces in `interface/`, with SQLite+markdown dual-write implementations in `client/`. Note: `SchemaService` in `service/schema_service.py` already depends on `ISchemaDb` (interface/schema_db.py) — reconcile naming here rather than introducing a second, differently-named interface for the same concept; extend/reuse the existing one if it already covers what entity_service needs, or rename consistently across both if not.
- `Entity` model moves from `domain/entity.py` to `model/entity.py`; exceptions (`EntityError`, `InvalidEntityError`, `UnknownSchemaError`, `EntityNotFoundError`) move alongside it, same pattern as document/schema.
- Old `services/entity.py`, `db/entity_repository.py` deleted once migrated.
- Unit tests for `EntityService` using mock stores.
Implementation Notes:
- Watch the naming collision: `services/document.py` defines its own `EntityNotFoundError`, distinct from entity service's own. Once both live under `model/`, make sure imports in document_service disambiguate cleanly (e.g. `model.entity.EntityNotFoundError` vs `model.document.EntityNotFoundError`, or collapse to one if that turns out cleaner — use judgement, but don't silently merge behavior that the current code intentionally kept separate without flagging it).
- This task and the document service task both touch entity existence checks — sequence them together or coordinate directly since `DocumentService` needs to check entity existence for link/unlink.

Task: Refactor linking into entity service
ACs:
- The rule-based candidate-matching logic currently in `services/linking.py` (`find_candidates`) is preserved and callable from wherever entity-linking candidate discovery is needed going forward.
- Given `find_candidates` is a pure function (no I/O, no DB), it doesn't need to become a class — style guide allows non-service pure logic, but it should live under `service/` (e.g. as a module-level function in `service/entity_service.py` or a small `service/linking.py` helper module) rather than staying in the legacy `services/` folder. Use judgement on whether it belongs as a static/module function beside `EntityService` or genuinely separate; document the choice isn't a hard call either way.
- Docstrings and the "future seam" comment about embeddings are preserved.
- Old `services/linking.py` deleted once migrated; tests ported over.
Implementation Notes:
- This is a small, low-risk task — mostly a file move plus import updates. Fine to bundle with the entity service task if one engineer picks up both, but listed separately since it can be done independently and in parallel.

Task: Build user-level vault registry (config dir + interface/client)
ACs:
- A new interface (e.g. `IVaultRegistry` in `interface/vault_registry.py`) exposes operations needed to track known vaults from a user-level (not vault-level) config location: register a vault (name + absolute path), list registered vaults, get a vault's path by name, remove a vault, get/set the default vault name.
- A concrete client implementation (e.g. `client/fs_vault_registry.py`) persists this to a user-level config directory (e.g. `~/.config/forte/vaults.yaml` or platform equivalent — follow existing config conventions in `services/config.py` if any exist, otherwise pick a reasonable default and note it).
- Registering a vault under a name that's already taken raises a typed error; looking up an unknown vault name raises a typed error; these live in `model/vault.py` alongside `VaultLayout`.
- Unit tests for the registry client (against a temp directory), and for typed-error behavior.
Implementation Notes:
- This is new functionality (not a pure refactor) — needed so `forte vault create personal .` can be run from any cwd and later commands (`forte schema add`, `forte doc ingest`, etc.) can resolve "the default vault" without requiring the user to `cd` into it first.
- Keep this interface narrow and storage-agnostic — it should not assume YAML specifically beyond the client implementation; `VaultService` (next task) should only see `IVaultRegistry`.
- Registering a vault does NOT create it — that's still `InitService`'s job. `forte vault create personal .` will call both: `InitService.init_vault()` then `IVaultRegistry.register()`. Sequence this task before the CLI commands task.

Task: Refactor discovery into VaultService, backed by vault registry
ACs:
- New `service/vault_service.py` defines `VaultService` as a class, constructor-injected with an `IVaultRegistry` (see prior task).
- `find_vault_root(start)` behavior from `services/discovery.py` is preserved as one method on `VaultService` (e.g. `find_vault_root`), including the git-style walk-up-from-cwd and `VaultNotFoundError` behavior — this stays supported as a fallback/override for running commands from inside a vault directory directly.
- New methods added to support the registry-backed flow described by the user: resolve the active vault without requiring cwd to be inside it — e.g. `get_default_vault() -> Path`, `list_vaults() -> list[...]`, `set_default_vault(name)`, `remove_vault(name)`. Exact method set is up to the implementing engineer, but must cover what the CLI commands task needs.
- Resolution order for "what vault am I operating on" is defined and documented in the class docstring: e.g. explicit `--vault <name>` flag (if passed by caller) > cwd walk-up (git-style, if inside a known vault) > registered default vault > error. Confirm this order with the user/PRD intent before finalizing if ambiguous — note the choice made and why in the docstring.
- `VaultNotFoundError` (and any new errors) live in `model/vault.py`.
- Old `services/discovery.py` deleted once migrated; unit tests cover both the walk-up path and the registry-default path, using a mock `IVaultRegistry`.
Implementation Notes:
- This is the "real service with many functions" the user called out — resist the urge to keep it a single-function passthrough; it should own the full "which vault, where" concern, not just replicate `find_vault_root`.
- Depends on the vault registry task being done first.

Task: Add `forte vault` CLI commands (create, list, set-default, remove)
ACs:
- `forte vault create <name> <path>` creates a vault at `<path>` (via `InitService`) and registers it under `<name>` (via `VaultService`/`IVaultRegistry`), so `forte vault create personal .` works from any directory.
- `forte vault list` prints registered vaults, indicating which is the default.
- `forte vault set-default <name>` updates the default vault.
- `forte vault remove <name>` removes a vault from the registry (does not delete files on disk — clarify this in the command's help text).
- Implemented as `CliVaultController` in `controller/cli_vault_controller.py`, following `CliInitController`/`CliSchemaController`'s pattern (class, services injected via constructor, `.group()`/`.command()` method returning the Click object), wired up in `main.py`.
- Typed exceptions from `VaultService`/`InitService` are mapped to clean Click error messages (no raw tracebacks) — follow whatever mapping convention `CliSchemaController` already uses.
Implementation Notes:
- Depends on both the vault registry and VaultService tasks being complete.
- Existing commands (`schema`, `doc`, `entity`) will eventually need to stop requiring cwd-inside-vault and instead resolve via `VaultService` — that broader migration is likely a separate future task; for this task, only wire up the new `vault` command group itself, don't touch existing command resolution.

Task: Wire everything into main.py, retire legacy services/db/domain/cli folders
ACs:
- `main.py` composition root wires `DocumentService`, `EntityService`, `VaultService`, their client implementations, and corresponding controllers, alongside the existing `InitService`/`SchemaService` wiring.
- Existing `doc`/`entity` CLI commands (currently presumably wired elsewhere, e.g. under `cli/` or not yet migrated) are moved to `controller/cli_document_controller.py` and `controller/cli_entity_controller.py` following the established naming/shape convention, and wired into `main.py`.
- Once all callers are migrated, the legacy `services/`, `db/`, and `domain/` folders are deleted entirely (verify nothing outside them still imports from them — grep before deleting). `cli/bulk_editor.py` and `cli/review_tui.py` are reviewed separately since they may be interactive TUI code that doesn't map cleanly to a controller — flag rather than force a fit if unclear.
- Full test suite passes after the folder deletions.
Implementation Notes:
- This is the integration/cleanup task — do last, once document/entity/vault service refactors and the vault CLI commands all exist.
- Use `grep -rn "from forte.services\|from forte.db\|from forte.domain\|from forte.cli"` (adjusted per remaining folder) to confirm nothing is left importing the legacy modules before deleting them.

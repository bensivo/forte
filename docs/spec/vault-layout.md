# Vault Layout Spec

Behavior spec for the `VaultLayout` domain module. Describes the well-known paths inside a Forte vault and the directories that `forte init` must create. `VaultLayout` is pure path arithmetic — it performs no filesystem I/O.

## Scenarios

### Scenario: Composing well-known paths from a vault root

```gherkin
Given a vault root path `/some/vault`
When a `VaultLayout` is constructed with that root
Then `forte_dir` is `/some/vault/.forte`
And `config_path` is `/some/vault/.forte/config.yaml`
And `db_path` is `/some/vault/.forte/index.db`
And `docs_raw_dir` is `/some/vault/docs/raw`
And `docs_processed_dir` is `/some/vault/docs/processed`
And `entities_dir` is `/some/vault/entities`
```

### Scenario: Composing paths from a relative root

```gherkin
Given a relative vault root path `my-vault`
When a `VaultLayout` is constructed with that root
Then every well-known path is composed relative to `my-vault` without being resolved to an absolute path
```

### Scenario: Listing directories that `forte init` must create

```gherkin
Given a `VaultLayout` for any root
When `all_dirs()` is called
Then the returned list contains exactly: `forte_dir`, `docs_dir`, `docs_raw_dir`, `docs_processed_dir`, `entities_dir`
And parent directories appear before their children (safe for sequential `mkdir`)
And per-schema subfolders under `entities/` (e.g. `entities/person/`) are NOT included — they are created lazily when schemas are added
```

### Scenario: Purity — no filesystem I/O

```gherkin
Given a `VaultLayout` for a root path that does not exist on disk
When any property is accessed or `all_dirs()` is called
Then no directories or files are created
And no filesystem reads occur
And no error is raised for the missing root
```

## Out of scope

- Actually creating the directories — that is the responsibility of the `forte init` driver.
- Creating per-schema `entities/<schema>/` subfolders — deferred to schema-registration flows.
- Validating that `root` is writable, empty, or otherwise suitable for a vault — validation lives in the init command.

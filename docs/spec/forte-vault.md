# `forte vault` Spec

Behavior spec for the `forte vault` command group — `forte vault create`, `forte vault list`, `forte vault show`, `forte vault remove`, and `forte vault set-default` — which manage the user-level registry of Forte vaults. A vault is a plain directory anywhere on disk containing `forte.db` (SQLite index), `forte.yaml` (per-vault config), and the `docs/raw/`, `docs/processed/`, `docs/staging/`, and `entities/` folders. There is no `.forte/` directory. Vaults are registered by name in a user-level registry at `~/.forte/config.yaml` (a `default:` key plus a `vaults:` name-to-absolute-path mapping), so a vault can be created, addressed, and removed from any working directory. Every other command group (`schema`, `entity`, `doc`, `agent`) operates on the default vault, or on the vault named by a `--vault <name>` option; see those specs for details.

## Scenarios

### Scenario: Create a vault in an empty directory

```gherkin
Given an empty directory at `/Users/ben/notes`
And no vault named `personal` is registered
When the user runs `forte vault create personal /Users/ben/notes`
Then the process creates `/Users/ben/notes/forte.db` as a SQLite database
And the SQLite database contains the tables `documents`, `schemas`, `entities`, `entity_field_values`, `mentions`, and `ingest_changes`
And the process creates `/Users/ben/notes/forte.yaml` with placeholder contents
And the process creates the `docs/raw/`, `docs/processed/`, and `docs/staging/` directories under `/Users/ben/notes`
And the process creates the `entities/` directory under `/Users/ben/notes`
And the process registers `personal` in `~/.forte/config.yaml` with the absolute path `/Users/ben/notes`
And the process prints a success message including the vault name `personal` and the absolute path `/Users/ben/notes`
And the process exits with status code 0
```

### Scenario: Create a vault using a relative path

```gherkin
Given the current working directory is `/Users/ben/notes`, which is empty
And no vault named `personal` is registered
When the user runs `forte vault create personal .`
Then the process registers `personal` with the resolved absolute path `/Users/ben/notes`, not the literal string `.`
And the process exits with status code 0
```

### Scenario: Create a vault in a directory with a conflicting `docs/` folder

```gherkin
Given a directory that already contains a `docs/` folder
And no `forte.db`, `forte.yaml`, or `entities/` exist in that directory
When the user runs `forte vault create personal <path>`
Then the process prints an error message naming the conflicting `docs/` folder
And the process exits with a non-zero status code
And no `forte.db` or `forte.yaml` is created
And no vault named `personal` is registered
And the pre-existing `docs/` folder and its contents are left untouched
```

### Scenario: Create a vault in a directory with a conflicting `entities/` folder

```gherkin
Given a directory that already contains an `entities/` folder
And no `forte.db`, `forte.yaml`, or `docs/` exist in that directory
When the user runs `forte vault create personal <path>`
Then the process prints an error message naming the conflicting `entities/` folder
And the process exits with a non-zero status code
And no vault named `personal` is registered
And the pre-existing `entities/` folder and its contents are left untouched
```

### Scenario: Create a vault in a directory with a conflicting `forte.db`

```gherkin
Given a directory that already contains a `forte.db` file
When the user runs `forte vault create personal <path>`
Then the process prints an error message naming the conflicting `forte.db` file
And the process exits with a non-zero status code
And no vault named `personal` is registered
And the pre-existing `forte.db` file is left untouched
```

### Scenario: Create a vault with a name that is already registered

```gherkin
Given a vault named `personal` is already registered, pointing at `/Users/ben/notes`
When the user runs `forte vault create personal /Users/ben/other-notes`
Then the process prints an error message indicating the vault name `personal` is already registered
And the process exits with a non-zero status code
And no files or directories are created under `/Users/ben/other-notes`
And the registered `personal` vault still points at `/Users/ben/notes`
```

### Scenario: Create a vault with an invalid name

```gherkin
Given no vault named `My Vault!` is registered
When the user runs `forte vault create` with a name that does not match the slug rule `^[a-z0-9][a-z0-9_-]*$` (for example one containing spaces, uppercase letters, or punctuation)
Then the process prints an error message indicating the name is not a valid vault name
And the process exits with a non-zero status code
And no vault is registered
And no files or directories are created at the target path
```

### Scenario: The first vault created becomes the default automatically

```gherkin
Given no vaults are registered and no default is set
When the user runs `forte vault create personal /Users/ben/notes`
Then the process exits with status code 0
And running `forte vault show personal` afterward reports it as the default
And running `forte schema list` (or any other vault-scoped command) with no `--vault` afterward operates on `personal`
```

### Scenario: Creating a second vault does not change the existing default

```gherkin
Given a vault named `personal` is registered and is the default
When the user runs `forte vault create work /Users/ben/work-notes`
Then the process exits with status code 0
And running `forte vault show personal` afterward still reports it as the default
And running `forte vault show work` afterward reports it as not the default
```

### Scenario: List vaults when several are registered

```gherkin
Given a vault named `personal` is registered at `/Users/ben/notes` and is the default
And a vault named `work` is registered at `/Users/ben/work-notes`
When the user runs `forte vault list`
Then the process prints one line for each vault including its name and absolute path
And the line for `personal` is marked as the default
And the line for `work` is not marked as the default
And the process exits with status code 0
```

### Scenario: List vaults when none are registered

```gherkin
Given no vaults are registered
When the user runs `forte vault list`
Then the process prints a friendly message indicating no vaults are registered yet
And the process exits with status code 0
```

### Scenario: Show a known vault

```gherkin
Given a vault named `personal` is registered at `/Users/ben/notes` and is the default
When the user runs `forte vault show personal`
Then the process prints the vault's name `personal`
And the process prints the vault's absolute path `/Users/ben/notes`
And the process prints that it is the default vault
And the process exits with status code 0
```

### Scenario: Show a vault that is not the default

```gherkin
Given a vault named `work` is registered at `/Users/ben/work-notes`
And `work` is not the default vault
When the user runs `forte vault show work`
Then the process prints the vault's name and absolute path
And the process prints that it is not the default vault
And the process exits with status code 0
```

### Scenario: Show an unknown vault name

```gherkin
Given no vault named `missing` is registered
When the user runs `forte vault show missing`
Then the process prints an error message indicating the vault was not found
And the process exits with a non-zero status code
```

### Scenario: Remove a non-default vault

```gherkin
Given a vault named `personal` is registered and is the default
And a vault named `work` is registered and is not the default
When the user runs `forte vault remove work --yes`
Then the process prints a confirmation message naming the removed vault `work`
And the process exits with status code 0
And running `forte vault list` afterward no longer shows `work`
And running `forte vault show personal` afterward still reports it as the default
And the directory that backed `work` on disk, and all files under it, are unchanged
```

### Scenario: Removing the default vault clears the default

```gherkin
Given a vault named `personal` is registered and is the default
And no other vault is registered
When the user runs `forte vault remove personal --yes`
Then the process exits with status code 0
And running `forte vault list` afterward shows no vaults
And running any vault-scoped command (e.g. `forte schema list`) with no `--vault` afterward fails with a "no default vault set" error
And the directory that backed `personal` on disk, and all files under it, are unchanged
```

### Scenario: Remove without confirmation prompts and aborts

```gherkin
Given a vault named `personal` is registered
When the user runs `forte vault remove personal` and does not confirm the prompt
Then the process prints an "Aborted." message
And the process exits with status code 0
And `personal` is still registered
```

### Scenario: The `--yes`/`-y` flag skips the confirmation prompt

```gherkin
Given a vault named `personal` is registered
When the user runs `forte vault remove personal --yes` (or `forte vault remove personal -y`)
Then the process does not prompt for confirmation
And the process prints a confirmation message naming the removed vault
And `personal` is no longer registered
```

### Scenario: Remove an unknown vault name

```gherkin
Given no vault named `missing` is registered
When the user runs `forte vault remove missing --yes`
Then the process prints an error message indicating the vault was not found
And the process exits with a non-zero status code
And the registry is unchanged
```

### Scenario: Set a different vault as the default

```gherkin
Given a vault named `personal` is registered and is the default
And a vault named `work` is registered and is not the default
When the user runs `forte vault set-default work`
Then the process prints a confirmation message naming the new default `work`
And the process exits with status code 0
And running `forte vault show work` afterward reports it as the default
And running `forte vault show personal` afterward reports it as not the default
```

### Scenario: Set the default to an unknown vault name

```gherkin
Given no vault named `missing` is registered
When the user runs `forte vault set-default missing`
Then the process prints an error message indicating the vault was not found
And the process exits with a non-zero status code
And the current default, if any, is unchanged
```

## Out of scope

- **`forte vault edit`** — there is no command to rename a vault, move its registered path, or otherwise edit its registry entry after creation. To point a name at a different directory, remove and re-create it.
- **Migrating pre-existing `.forte/` vaults** — Forte is pre-release; there is no migration path from the old `.forte/`-based layout to the new `forte.db`/`forte.yaml` layout. Vaults created under the old model are not recognized and must be re-created.
- **Deleting vault contents on `remove`** — `forte vault remove` only unregisters a vault from `~/.forte/config.yaml`; it never deletes `forte.db`, `forte.yaml`, or any files under the vault's directory. Deleting the directory, if desired, is a manual filesystem operation.
- **Multiple registries / registry location override** — the registry always lives at `~/.forte/config.yaml`; there is no flag or environment variable to point it elsewhere at MVP.

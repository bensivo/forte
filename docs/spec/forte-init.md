# `forte init` Spec

Behavior spec for the `forte init` command, which initializes a new Forte vault in the current working directory.

## Scenarios

### Scenario: Init in an empty directory

```gherkin
Given the current working directory is empty
And no `.forte/` folder exists
When the user runs `forte init`
Then the process creates the `.forte/` directory
And the process creates `.forte/config.yaml` with placeholder contents
And the process creates `.forte/index.db` as a SQLite database
And the SQLite database contains the tables `documents`, `schemas`, `entities`, `entity_field_values`, `mentions`, and `ingest_changes`
And the process creates the `docs/raw/` directory
And the process creates the `docs/processed/` directory
And the process creates the `entities/` directory
And the process prints a success message including the absolute vault path
And the process exits with status code 0
```

### Scenario: Init when a vault already exists

```gherkin
Given the current working directory already contains a `.forte/` folder
When the user runs `forte init`
Then the process prints an error message indicating the vault already exists
And the process exits with a non-zero status code
And no files under the existing `.forte/` folder are modified
```

### Scenario: Init when a conflicting top-level folder already exists

```gherkin
Given the current working directory contains a `docs/` folder (or an `entities/` folder)
And no `.forte/` folder exists
When the user runs `forte init`
Then the process prints an error message naming the conflicting folder and asking the user to run in an empty directory
And the process exits with a non-zero status code
And no files or directories are created
And the pre-existing conflicting folder and its contents are left untouched
```

### Scenario: Init in a non-empty directory without a vault

```gherkin
Given the current working directory contains pre-existing files (e.g. `README.md`, `notes.txt`)
And no `.forte/` folder exists
When the user runs `forte init`
Then the process creates the full vault layout alongside the existing files
And the pre-existing files are left untouched
And the process exits with status code 0
```

## Out of scope

- Re-initializing or repairing a partially-created vault — MVP treats a present `.forte/` as an unconditional block.
- Custom vault paths via flags — `init` always targets the current working directory at MVP.
- Populating `config.yaml` with real keys — placeholder only until a feature needs one.

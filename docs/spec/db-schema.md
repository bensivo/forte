# SQLite Schema Bootstrap Spec

Behavior spec for `forte.db.schema.initialize_database`, which creates a fresh SQLite index database for a Forte vault.

## Scenarios

### Scenario: Initializing a new database

```gherkin
Given a path where no file yet exists
When `initialize_database` is called with that path
Then a SQLite database file is created at that path
And the database contains the table `documents`
And the database contains the table `schemas`
And the database contains the table `entities`
And the database contains the table `entity_field_values`
And the database contains the table `mentions`
And the database contains the table `ingest_changes`
```

### Scenario: Refusing to overwrite an existing database

```gherkin
Given a file already exists at the target path
When `initialize_database` is called with that path
Then the call raises `FileExistsError`
And the existing file is not modified
```

## Out of scope for MVP

- `entity_embeddings` table — deferred until the embeddings storage decision is made; not created by this task.
- Indices — none are created at MVP; will be added when a query obviously needs one.
- Migrations — no migration framework at MVP; only fresh-init DDL is supported.

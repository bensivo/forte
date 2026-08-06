# `forte schema` Spec

Behavior spec for the `forte schema` command group — `forte schema add`, `forte schema list`, and `forte schema remove` — which define, inspect, and delete the entity kinds (schemas) available in a Forte vault. A schema is a named entity kind plus an ordered list of free-text field names; each schema is backed by a row in the SQLite `schemas` table and a matching `entities/<name>/` folder. These commands operate on the default vault registered in `~/.forte/config.yaml`, or on the vault named by a `--vault <name>` option, regardless of the current working directory. See [docs/spec/forte-vault.md](./forte-vault.md) for how vaults are created and registered.

## Scenarios

### Scenario: Add a schema with one or more fields

```gherkin
Given a default vault is set
And no schema named `person` exists
When the user runs `forte schema add person --field employer --field role`
Then the process prints a success message naming the schema and its fields
And the process exits with status code 0
And the vault contains an `entities/person/` directory
And running `forte schema list` afterward shows `person` with the fields `employer` and `role`
```

### Scenario: Add a schema with no fields

```gherkin
Given a default vault is set
And no schema named `note` exists
When the user runs `forte schema add note`
Then the process prints a success message for the schema `note`
And the process exits with status code 0
And the vault contains an `entities/note/` directory
And running `forte schema list` afterward shows `note` with no user-defined fields
```

### Scenario: Add a schema whose name already exists

```gherkin
Given a default vault is set
And a schema named `person` already exists with fields `employer` and `role`
When the user runs `forte schema add person --field email`
Then the process prints an error message indicating the schema already exists
And the process exits with a non-zero status code
And the existing `person` schema still has exactly the fields `employer` and `role`
```

### Scenario: Add a schema that reserves `name` as a field

```gherkin
Given a default vault is set
When the user runs `forte schema add person --field name`
Then the process prints an error message indicating `name` is a reserved built-in field
And the process exits with a non-zero status code
And no `person` schema is created
And no `entities/person/` directory is created
```

### Scenario: Add a schema that reserves `aliases` as a field

```gherkin
Given a default vault is set
When the user runs `forte schema add person --field aliases`
Then the process prints an error message indicating `aliases` is a reserved built-in field
And the process exits with a non-zero status code
And no `person` schema is created
And no `entities/person/` directory is created
```

### Scenario: Add a schema with duplicate field flags

```gherkin
Given a default vault is set
When the user runs `forte schema add person --field role --field role`
Then the process prints an error message indicating a field is duplicated
And the process exits with a non-zero status code
And no `person` schema is created
And no `entities/person/` directory is created
```

### Scenario: Add a schema with an invalid name

```gherkin
Given a default vault is set
When the user runs `forte schema add` with a name that is not a folder-safe slug (for example one containing spaces, slashes, or uppercase letters)
Then the process prints an error message indicating the name is not a valid schema name
And the process exits with a non-zero status code
And no schema is created
And no corresponding directory is created under `entities/`
```

### Scenario: List schemas in a vault with several defined

```gherkin
Given a default vault is set
And a schema named `person` exists with fields `employer` and `role`
And a schema named `project` exists with fields `status` and `owner`
When the user runs `forte schema list`
Then the process prints `person` along with its fields `employer` and `role`
And the process prints `project` along with its fields `status` and `owner`
And the process exits with status code 0
```

### Scenario: List schemas in a vault with none defined

```gherkin
Given a default vault is set
And no schemas are defined
When the user runs `forte schema list`
Then the process prints a friendly message indicating no schemas are defined
And the process exits with status code 0
```

### Scenario: Remove an existing schema

```gherkin
Given a default vault is set
And a schema named `person` exists
And no entities of the `person` schema exist
When the user runs `forte schema remove person --yes`
Then the process prints a success message indicating the schema was removed
And the process exits with status code 0
And the `person` row is gone from the vault's schemas
And the `entities/person/` directory no longer exists
And running `forte schema list` afterward does not show `person`
```

### Scenario: Remove a non-existent schema

```gherkin
Given a default vault is set
And no schema named `person` exists
When the user runs `forte schema remove person --yes`
Then the process prints an error message indicating the schema was not found
And the process exits with a non-zero status code
```

### Scenario: Run a schema subcommand with no default vault set and no `--vault`

```gherkin
Given no default vault is registered in `~/.forte/config.yaml`
When the user runs any `forte schema` subcommand (`add`, `list`, or `remove`) with no `--vault` option
Then the process prints a clear error message telling the user to run `forte vault create` or `forte vault set-default`
And the process exits with a non-zero status code
And no schema is created, listed, or removed
```

### Scenario: Run a schema subcommand against a non-default vault via `--vault`

```gherkin
Given a vault named `personal` is the default and contains no schemas
And a vault named `work` is registered and contains a schema named `person` with fields `employer` and `role`
When the user runs `forte schema list --vault work`
Then the process prints `person` along with its fields `employer` and `role`
And the process exits with status code 0
And the default vault `personal` is unaffected
```

### Scenario: Run a schema subcommand with an unknown `--vault` name

```gherkin
Given no vault named `missing` is registered
When the user runs `forte schema list --vault missing`
Then the process prints an error message indicating the vault was not found
And the process exits with a non-zero status code
```

## Out of scope

- **Schema-mutation cascade** (back-filling a new field or stripping a removed field across existing entities) — this belongs to future `forte schema add-field` / `forte schema remove-field` commands, which mutate a schema's field set in place. Whole-schema `add` and `remove` covered here do not touch entities of other schemas, and `add`/`remove` of a whole schema is only ever done when it has no dependent entities (see below).
- **Removing a schema that still has entities** — at MVP, `forte schema remove` of a schema that still has entities is blocked with a clear error instructing the user to remove those entities first, and removes nothing. This is forward-looking: entity-creation commands (`forte entity add`, `forte doc ingest`) do not exist yet, so in practice a schema at MVP can always be removed, but the guard prevents orphaning entities once those commands land.
- **Field types and validation** — fields are free-text names only at MVP; there is no per-field type system, and field values are not validated here.
- **Editing a schema's fields after creation** — changing the field set of an existing schema is deferred to the anticipated `add-field` / `remove-field` commands.

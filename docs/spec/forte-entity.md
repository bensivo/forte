# `forte entity` Spec

Behavior spec for the `forte entity` command group — `forte entity add`, `forte entity list`, `forte entity show`, `forte entity edit`, and `forte entity remove` — which create, inspect, edit, and delete the entities that make up a Forte knowledge base. An entity is an instance of a defined schema: it has a built-in `name` and list of `aliases`, plus exactly that schema's user-defined fields (empty values allowed, no missing or extra fields). Unlike schemas, entities are part of the human-readable knowledge base, so every write **dual-writes** to a markdown file at `entities/<schema>/<slug>.md` (YAML frontmatter carrying `name`/`aliases` and the schema fields, followed by a free-form body) AND a row in the SQLite `entities` table. Ids are integers assigned by SQLite. These commands operate on an existing vault, discovered git-style by walking up from the current working directory to find a `.forte/` directory.

## Scenarios

### Scenario: Add an entity with a name and field values

```gherkin
Given the current working directory is inside a Forte vault
And a schema named `person` exists with fields `employer` and `role`
When the user runs `forte entity add person --name "Ben Sivongxay" --field employer=Acme --field role=Engineer`
Then the process prints a success message including the assigned integer id and the entity name
And the process exits with status code 0
And the vault contains a markdown file under `entities/person/` for the entity
And the markdown frontmatter carries `name`, `aliases`, and the fields `employer` and `role` with their values
And a row for the entity is present in the `entities` table
And running `forte entity list` afterward shows the entity with its id, schema, and name
And running `forte entity show <id>` afterward shows the name and the field values
```

### Scenario: Add an entity with only a name

```gherkin
Given the current working directory is inside a Forte vault
And a schema named `person` exists with fields `employer` and `role`
When the user runs `forte entity add person --name "Ben Sivongxay"`
Then the process exits with status code 0
And the stored entity carries every schema field back-filled to an empty value
And the stored entity carries the built-in `name` and an empty `aliases` list
And running `forte entity show <id>` afterward lists `employer` and `role` each with an empty value
```

### Scenario: Add an entity for a schema that does not exist

```gherkin
Given the current working directory is inside a Forte vault
And no schema named `person` exists
When the user runs `forte entity add person --name "Ben"`
Then the process prints an error message indicating the schema is unknown
And the process exits with a non-zero status code
And no markdown file is created under `entities/`
And no row is inserted into the `entities` table
```

### Scenario: Add an entity with a field not defined by the schema

```gherkin
Given the current working directory is inside a Forte vault
And a schema named `person` exists with fields `employer` and `role`
When the user runs `forte entity add person --name "Ben" --field height=tall`
Then the process prints an error message indicating `height` is not a field of the schema
And the process exits with a non-zero status code
And no markdown file is created for the entity
And no row is inserted into the `entities` table
```

### Scenario: Add an entity with a missing or empty name

```gherkin
Given the current working directory is inside a Forte vault
And a schema named `person` exists with fields `employer` and `role`
When the user runs `forte entity add person` with no `--name`, or with an empty `--name ""`
Then the process prints an error message indicating a non-empty name is required
And the process exits with a non-zero status code
And no entity is created
```

### Scenario: Add an entity with aliases

```gherkin
Given the current working directory is inside a Forte vault
And a schema named `person` exists with fields `employer` and `role`
When the user runs `forte entity add person --name "Ben Sivongxay" --alias "Ben" --alias "Ben S."`
Then the process exits with status code 0
And the stored entity's aliases are `Ben` and `Ben S.`
And running `forte entity show <id>` afterward lists those aliases
```

### Scenario: List entities in a vault with several defined

```gherkin
Given the current working directory is inside a Forte vault
And a `person` entity and a `project` entity have been added
When the user runs `forte entity list`
Then the process prints one line per entity including its id, schema, and name
And both the `person` entity and the `project` entity appear
And the process exits with status code 0
```

### Scenario: List entities filtered by schema

```gherkin
Given the current working directory is inside a Forte vault
And two `person` entities and one `project` entity have been added
When the user runs `forte entity list --schema person`
Then the process prints only the two `person` entities
And the `project` entity does not appear
And the process exits with status code 0
```

### Scenario: List entities filtered by an unknown schema

```gherkin
Given the current working directory is inside a Forte vault
And no schema named `widget` exists
When the user runs `forte entity list --schema widget`
Then the process prints an error message indicating the schema is unknown
And the process exits with a non-zero status code
```

### Scenario: List entities in a vault with none defined

```gherkin
Given the current working directory is inside a Forte vault
And no entities have been added
When the user runs `forte entity list`
Then the process prints a friendly message indicating there are no entities yet
And the process exits with status code 0
```

### Scenario: Show an entity

```gherkin
Given the current working directory is inside a Forte vault
And a `person` entity has been added with a name, aliases, and field values
When the user runs `forte entity show <id>`
Then the process prints the entity's id, schema, and name
And the process prints the entity's aliases
And the process prints each schema field with its (possibly empty) value, in schema field order
And the process prints the free-form body if present
And the process exits with status code 0
```

### Scenario: Show a non-existent entity

```gherkin
Given the current working directory is inside a Forte vault
And no entity with id `999` exists
When the user runs `forte entity show 999`
Then the process prints an error message indicating the entity was not found
And the process exits with a non-zero status code
```

### Scenario: Edit an entity's name, fields, and aliases

```gherkin
Given the current working directory is inside a Forte vault
And a `person` entity with fields `employer` and `role` has been added
When the user runs `forte entity edit <id> --name "Ben S." --set role=Engineer --add-alias "Benny" --remove-alias "Ben"`
Then the process prints a confirmation message
And the process exits with status code 0
And running `forte entity show <id>` afterward reflects the new name, the updated `role` value, and the changed alias list
And the on-disk markdown file reflects the same changes
```

### Scenario: Edit an entity's name renames the markdown file

```gherkin
Given the current working directory is inside a Forte vault
And a `person` entity named `Ben Sivongxay` has been added
When the user runs `forte entity edit <id> --name "Benjamin Sivongxay"`
Then the process exits with status code 0
And a markdown file matching the new name's slug exists under `entities/person/`
And the markdown file for the old name's slug no longer exists
And the entity's stored `file_path` reflects the new filename
```

### Scenario: Edit an entity with a field not defined by the schema

```gherkin
Given the current working directory is inside a Forte vault
And a `person` entity with fields `employer` and `role` has been added
When the user runs `forte entity edit <id> --set height=tall`
Then the process prints an error message indicating `height` is not a field of the schema
And the process exits with a non-zero status code
And the entity is unchanged in both the markdown file and the `entities` table
```

### Scenario: Edit a non-existent entity

```gherkin
Given the current working directory is inside a Forte vault
And no entity with id `999` exists
When the user runs `forte entity edit 999 --name "Whoever"`
Then the process prints an error message indicating the entity was not found
And the process exits with a non-zero status code
And nothing is created or changed
```

### Scenario: Remove an entity

```gherkin
Given the current working directory is inside a Forte vault
And a `person` entity has been added
When the user runs `forte entity remove <id> --yes`
Then the process prints a success message indicating the entity was removed
And the process exits with status code 0
And the entity's markdown file no longer exists
And the entity's row is gone from the `entities` table
And running `forte entity list` afterward does not show the entity
And running `forte entity show <id>` afterward exits with a non-zero status code
```

### Scenario: Remove a non-existent entity

```gherkin
Given the current working directory is inside a Forte vault
And no entity with id `999` exists
When the user runs `forte entity remove 999 --yes`
Then the process prints an error message indicating the entity was not found
And the process exits with a non-zero status code
And nothing is removed
```

### Scenario: Run an entity subcommand outside a vault

```gherkin
Given the current working directory is not inside a Forte vault
And no `.forte/` directory exists in the current directory or any ancestor
When the user runs any `forte entity` subcommand (`add`, `list`, `show`, `edit`, or `remove`)
Then the process prints an error message indicating the user is not inside a Forte vault
And the process exits with a non-zero status code
And no entity is created, listed, shown, edited, or removed
```

## Out of scope

- **`forte entity search`** — superseded by the unified `forte search` command, which searches both entities and documents together. See [docs/spec/forte-search.md](forte-search.md).
- **Linked docs / mentions in `entity show`** — the PRD describes `entity show` as displaying an entity's fields *and* the documents that mention it. Mentions are produced by `forte doc ingest`, which does not exist yet, so the linked-docs section is empty for now (either omitted or shown as an explicit empty placeholder). Mention querying is not built in this batch.
- **Schema-mutation cascade onto existing entities** — adding or removing a field on a schema and back-filling or stripping that field across its existing entities belongs to future `forte schema add-field` / `remove-field` commands. This batch only guarantees the structural field-set invariant holds at entity write time against the schema as it exists then.
- **Reconciling hand-edits to markdown that bypass the CLI** — at MVP, editing an entity's markdown file directly (outside `forte entity edit`) is not detected or auto-reconciled with the SQLite index; drift is a known non-goal.
- **`$EDITOR`-based editing** — `forte entity edit` uses a deterministic, flag-based interface (`--name` / `--set` / `--add-alias` / `--remove-alias`). Opening the markdown file in `$EDITOR` and re-parsing it is a natural richer alternative but is not built here.
- **Field types and value validation** — field values are free-text strings with no per-field type or value validation; only the *set of field names* is constrained (exactly the schema's fields).

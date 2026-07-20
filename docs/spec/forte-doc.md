# `forte doc` Spec

Behavior spec for the `forte doc` command group — `forte doc ingest`, `forte doc list`, `forte doc show`, `forte doc link`, `forte doc unlink`, and `forte doc remove` — which bring raw documents into a Forte vault and manually associate them with entities. **Scope cut for this batch:** `doc ingest` performs only the first pipeline step (copy the source into `docs/raw/`) plus a new "extract raw text" step that writes the extracted text into `docs/processed/` with metadata frontmatter, then stops — there is no LLM call, no automatic entity extraction, no entity-linking proposals, and no review TUI yet. Because automatic linking isn't implemented yet, this batch also adds `doc link`/`doc unlink`, manual commands that directly create or remove rows in the `mentions` table so a user (or agent) can hand-link a processed doc to an existing entity. Unlike entities, documents are **not** dual-written as structured, editable knowledge: a doc has exactly two on-disk artifacts (the immutable raw copy and the derived processed copy) plus one row in the SQLite `documents` table; `docs/processed/` is regenerated output, not something a user hand-maintains. These commands operate on an existing vault, discovered git-style by walking up from the current working directory to find a `.forte/` directory.

## Scenarios

### Scenario: Ingest a Markdown or plain-text file

```gherkin
Given the current working directory is inside a Forte vault
And a file `kickoff.md` exists on disk outside the vault's `docs/raw/` directory
When the user runs `forte doc ingest kickoff.md`
Then the process prints a success message including the assigned integer id and the document's name
And the document's name defaults to the source filename, `kickoff.md`, since `--name` was not given
And the process exits with status code 0
And the vault's `docs/raw/` directory contains a copy of `kickoff.md`
And the vault's `docs/processed/` directory contains a new markdown file
And that processed file's frontmatter carries the document's name, source path, a content hash, and an ingested timestamp
And that processed file's body contains the verbatim text of `kickoff.md`
And a row for the document is present in the `documents` table with the assigned id and name
And running `forte doc list` and `forte doc show <id>` afterward both display the document's name
```

### Scenario: Ingest a file with an explicit name

```gherkin
Given the current working directory is inside a Forte vault
And a file `kickoff.md` exists on disk outside the vault
When the user runs `forte doc ingest kickoff.md --name "Kickoff Notes"`
Then the process prints a success message including the assigned integer id and the name "Kickoff Notes"
And the process exits with status code 0
And running `forte doc list` and `forte doc show <id>` afterward both display "Kickoff Notes", not the filename
```

### Scenario: Ingest a Word or PDF document

```gherkin
Given the current working directory is inside a Forte vault
And a file `report.docx` (or `report.pdf`) exists on disk outside the vault
When the user runs `forte doc ingest report.docx`
Then the process exits with status code 0
And the vault's `docs/processed/` directory contains a new markdown file
And that processed file's body contains the readable text extracted from the document, not raw binary content
And a row for the document is present in the `documents` table with the assigned id
```

### Scenario: Ingest a path that does not exist

```gherkin
Given the current working directory is inside a Forte vault
And no file exists at `missing.md`
When the user runs `forte doc ingest missing.md`
Then the process prints an error message indicating the source file was not found
And the process exits with a non-zero status code
And nothing is written to `docs/raw/` or `docs/processed/`
And no row is added to the `documents` table
```

### Scenario: Ingest a file of an unsupported type

```gherkin
Given the current working directory is inside a Forte vault
And a file `diagram.png` exists on disk outside the vault
When the user runs `forte doc ingest diagram.png`
Then the process prints an error message indicating `.png` files are not supported
And the process exits with a non-zero status code
And nothing is written to `docs/raw/` or `docs/processed/`
And no row is added to the `documents` table
```

### Scenario: Re-ingest an unchanged file is a no-op

```gherkin
Given the current working directory is inside a Forte vault
And `forte doc ingest kickoff.md` has already been run successfully, assigning it id 7
And the file at `kickoff.md` has not changed since (same source path and same content hash)
When the user runs `forte doc ingest kickoff.md` again
Then the process prints a message reporting the existing document id 7 rather than creating a new one
And the process exits with status code 0
And no new file is written to `docs/raw/` or `docs/processed/`
And no new row is added to the `documents` table
And running `forte doc list` afterward still shows exactly one document for `kickoff.md`
```

### Scenario: List documents in a vault with several ingested

```gherkin
Given the current working directory is inside a Forte vault
And `kickoff.md` and `report.docx` have both been ingested
When the user runs `forte doc list`
Then the process prints one line for each document including its id and source filename
And the process exits with status code 0
```

### Scenario: List documents in a vault with none ingested

```gherkin
Given the current working directory is inside a Forte vault
And no documents have been ingested
When the user runs `forte doc list`
Then the process prints a friendly message indicating no documents exist
And the process exits with status code 0
```

### Scenario: Show an existing document

```gherkin
Given the current working directory is inside a Forte vault
And `kickoff.md` has been ingested and assigned id 7
When the user runs `forte doc show 7`
Then the process prints the document's id, source path, and ingested timestamp
And the process prints the document's extracted text (inline, or the path to its processed file)
And the process exits with status code 0
```

### Scenario: Show a non-existent document

```gherkin
Given the current working directory is inside a Forte vault
And no document with id 99 exists
When the user runs `forte doc show 99`
Then the process prints an error message indicating the document was not found
And the process exits with a non-zero status code
```

### Scenario: Link a document to an entity

```gherkin
Given the current working directory is inside a Forte vault
And a document with id 7 exists
And an entity with id 3 exists
When the user runs `forte doc link 7 3`
Then the process prints a confirmation message naming the document and entity ids
And the process exits with status code 0
And a row linking doc 7 and entity 3 is present in the `mentions` table
And running `forte doc show 7` afterward lists entity id 3 among its linked entities
```

### Scenario: Link with a non-existent document or entity id

```gherkin
Given the current working directory is inside a Forte vault
And no document with id 99 exists
And an entity with id 3 exists
When the user runs `forte doc link 99 3`
Then the process prints an error message indicating the document was not found
And the process exits with a non-zero status code
And no row is added to the `mentions` table
```

```gherkin
Given the current working directory is inside a Forte vault
And a document with id 7 exists
And no entity with id 99 exists
When the user runs `forte doc link 7 99`
Then the process prints an error message indicating the entity was not found
And the process exits with a non-zero status code
And no row is added to the `mentions` table
```

### Scenario: Link the same document/entity pair twice is a no-op

```gherkin
Given the current working directory is inside a Forte vault
And a document with id 7 is already linked to entity id 3
When the user runs `forte doc link 7 3` again
Then the process prints a confirmation message as if the link succeeded
And the process exits with status code 0
And exactly one row linking doc 7 and entity 3 is present in the `mentions` table (no duplicate is created)
```

### Scenario: Unlink a linked document and entity

```gherkin
Given the current working directory is inside a Forte vault
And a document with id 7 is linked to entity id 3
When the user runs `forte doc unlink 7 3`
Then the process prints a confirmation message naming the document and entity ids
And the process exits with status code 0
And the row linking doc 7 and entity 3 is no longer present in the `mentions` table
And running `forte doc show 7` afterward no longer lists entity id 3 among its linked entities
```

### Scenario: Unlink a pair that is not linked is a no-op

```gherkin
Given the current working directory is inside a Forte vault
And a document with id 7 exists
And an entity with id 3 exists
And doc 7 and entity 3 are not currently linked
When the user runs `forte doc unlink 7 3`
Then the process prints a confirmation message as if the unlink succeeded
And the process exits with status code 0
And the `mentions` table still contains no row linking doc 7 and entity 3
```

### Scenario: Unlink with a non-existent document or entity id

```gherkin
Given the current working directory is inside a Forte vault
And no document with id 99 exists
And an entity with id 3 exists
When the user runs `forte doc unlink 99 3`
Then the process prints an error message indicating the document was not found
And the process exits with a non-zero status code
```

```gherkin
Given the current working directory is inside a Forte vault
And a document with id 7 exists
And no entity with id 99 exists
When the user runs `forte doc unlink 7 99`
Then the process prints an error message indicating the entity was not found
And the process exits with a non-zero status code
```

### Scenario: Remove an existing document

```gherkin
Given the current working directory is inside a Forte vault
And a document with id 7 exists, with a raw file in `docs/raw/` and a processed file in `docs/processed/`
When the user runs `forte doc remove 7` and confirms the prompt
Then the process prints a confirmation message naming the document's id and name
And the process exits with status code 0
And the document's raw file is deleted from `docs/raw/`
And the document's processed file is deleted from `docs/processed/`
And the row for document 7 is no longer present in the `documents` table
And any rows in the `mentions` table referencing document 7 are gone
And running `forte doc list` afterward no longer includes document 7
And running `forte doc show 7` afterward reports the document was not found
```

### Scenario: Removing a document with linked entities does not affect those entities

```gherkin
Given the current working directory is inside a Forte vault
And a document with id 7 is linked to entity id 3
When the user runs `forte doc remove 7 --yes`
Then the process exits with status code 0
And the row linking doc 7 and entity 3 is no longer present in the `mentions` table
And entity id 3 itself still exists in the `entities` table, unmodified
And running `forte entity show 3` afterward still displays entity 3's name, schema, and fields as before
```

### Scenario: Remove a non-existent document

```gherkin
Given the current working directory is inside a Forte vault
And no document with id 99 exists
When the user runs `forte doc remove 99`
Then the process prints an error message indicating the document was not found
And the process exits with a non-zero status code
And no files are deleted from `docs/raw/` or `docs/processed/`
And no row is removed from the `documents` table
```

### Scenario: Remove without confirmation prompts and aborts

```gherkin
Given the current working directory is inside a Forte vault
And a document with id 7 exists
When the user runs `forte doc remove 7` and does not confirm the prompt
Then the process prints an "Aborted." message
And the process exits with status code 0
And the document's raw and processed files are still present on disk
And the row for document 7 is still present in the `documents` table
```

### Scenario: The `--yes`/`-y` flag skips the confirmation prompt

```gherkin
Given the current working directory is inside a Forte vault
And a document with id 7 exists
When the user runs `forte doc remove 7 --yes` (or `forte doc remove 7 -y`)
Then the process does not prompt for confirmation
And the process prints a confirmation message naming the document's id and name
And the process exits with status code 0
And the document is removed as in the "Remove an existing document" scenario
```

### Scenario: Run a doc subcommand outside a vault

```gherkin
Given the current working directory is not inside a Forte vault
And no `.forte/` directory exists in the current directory or any ancestor
When the user runs any `forte doc` subcommand (`ingest`, `list`, `show`, `link`, `unlink`, or `remove`)
Then the process prints an error message indicating the user is not inside a Forte vault
And the process exits with a non-zero status code
And no document is ingested, listed, shown, linked, unlinked, or removed
```

## Out of scope

- **Entity extraction from doc content** — no LLM call inspects a document's text to propose entities or field values in this batch.
- **Entity linking proposals** — `mentions` rows are only created/removed directly and manually via `doc link`/`doc unlink`; there is no automatic proposal step.
- **Field extraction** — no extraction of structured field values from documents.
- **The review TUI** — there is nothing to approve yet, so no interactive review flow exists for docs.
- **`ingest_changes` / resumable ingest** — this batch's `ingest` is a single atomic step (copy + extract + record), not a multi-step pipeline with persisted intermediate proposals.
- **`--yes` auto-approve flag** — not applicable since there is no proposal step to approve.
- **`doc show` displaying full entity details** — it lists linked entity ids only; richer display (entity name, schema, fields) is deferred.
- **OCR, audio, web, and email ingestion** — `doc ingest` only supports `.md`, `.txt`, `.docx`, and `.pdf` in this batch.

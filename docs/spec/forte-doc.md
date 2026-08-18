# `forte doc` Spec

Behavior spec for the `forte doc` command group — `forte doc ingest`, `forte doc create`, `forte doc list`, `forte doc show`, `forte doc search`, `forte doc link`, `forte doc link-interactive`, `forte doc unlink`, and `forte doc remove` — which bring raw documents into a Forte vault and manually associate them with entities. **Scope cut for this batch:** `doc ingest` performs only the first pipeline step (copy the source into `docs/raw/`) plus a new "extract raw text" step that writes the extracted text into `docs/processed/` with metadata frontmatter, then stops — there is no LLM call, no automatic entity extraction, no entity-linking proposals, and no review TUI yet. Because automatic linking isn't implemented yet, this batch also adds `doc link`/`doc unlink`, manual commands that directly create or remove rows in the `mentions` table so a user (or agent) can hand-link a processed doc to an existing entity, plus `doc link-interactive`, an interactive prompt that picks entities by typing a partial name instead of an id. Both `doc create` and `doc ingest` are **two-step flows**: the document is stored first (via the editor, or via the raw-copy/extract pipeline), and only once it exists on disk and in the `documents` table does a second step offer the same interactive link prompt described under `forte doc link-interactive`; both accept `--no-link` to skip that second step. Unlike entities, documents are **not** dual-written as structured, editable knowledge: a doc has exactly two on-disk artifacts (the immutable raw copy and the derived processed copy) plus one row in the SQLite `documents` table; `docs/processed/` is regenerated output, not something a user hand-maintains. These commands operate on the default vault registered in `~/.forte/config.yaml`, or on the vault named by a `--vault <name>` option, regardless of the current working directory. See [docs/spec/forte-vault.md](./forte-vault.md) for how vaults are created and registered.

## Scenarios

### Scenario: Ingest a Markdown or plain-text file

```gherkin
Given a default vault is set
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
Given a default vault is set
And a file `kickoff.md` exists on disk outside the vault
When the user runs `forte doc ingest kickoff.md --name "Kickoff Notes"`
Then the process prints a success message including the assigned integer id and the name "Kickoff Notes"
And the process exits with status code 0
And running `forte doc list` and `forte doc show <id>` afterward both display "Kickoff Notes", not the filename
```

### Scenario: Ingest a Word or PDF document

```gherkin
Given a default vault is set
And a file `report.docx` (or `report.pdf`) exists on disk outside the vault
When the user runs `forte doc ingest report.docx`
Then the process exits with status code 0
And the vault's `docs/processed/` directory contains a new markdown file
And that processed file's body contains the readable text extracted from the document, not raw binary content
And a row for the document is present in the `documents` table with the assigned id
```

### Scenario: Ingest a path that does not exist

```gherkin
Given a default vault is set
And no file exists at `missing.md`
When the user runs `forte doc ingest missing.md`
Then the process prints an error message indicating the source file was not found
And the process exits with a non-zero status code
And nothing is written to `docs/raw/` or `docs/processed/`
And no row is added to the `documents` table
```

### Scenario: Ingest a file of an unsupported type

```gherkin
Given a default vault is set
And a file `diagram.png` exists on disk outside the vault
When the user runs `forte doc ingest diagram.png`
Then the process prints an error message indicating `.png` files are not supported
And the process exits with a non-zero status code
And nothing is written to `docs/raw/` or `docs/processed/`
And no row is added to the `documents` table
```

### Scenario: Re-ingest an unchanged file is a no-op

```gherkin
Given a default vault is set
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
Given a default vault is set
And `kickoff.md` and `report.docx` have both been ingested
When the user runs `forte doc list`
Then the process prints one line for each document including its id and source filename
And the process exits with status code 0
```

### Scenario: List documents in a vault with none ingested

```gherkin
Given a default vault is set
And no documents have been ingested
When the user runs `forte doc list`
Then the process prints a friendly message indicating no documents exist
And the process exits with status code 0
```

### Scenario: Show an existing document

```gherkin
Given a default vault is set
And `kickoff.md` has been ingested and assigned id 7
When the user runs `forte doc show 7`
Then the process prints the document's id, source path, and ingested timestamp
And the process prints the document's extracted text (inline, or the path to its processed file)
And the process exits with status code 0
```

### Scenario: Show a non-existent document

```gherkin
Given a default vault is set
And no document with id 99 exists
When the user runs `forte doc show 99`
Then the process prints an error message indicating the document was not found
And the process exits with a non-zero status code
```

## `forte doc search`

`forte doc search` is literal/regex full-text search over document bodies — the VSCode/Obsidian
"search in files" experience, running entirely locally against the vault's `docs/processed/`
text. It is deliberately **not** the deferred semantic `entity search` described in
[docs/solution-design.md](./solution-design.md): there is no LLM call, no embeddings, and no
network access, only pattern matching against text already on disk. Results are grouped by
document, each document's matches are printed in ascending line order, and line numbers are
1-based against the document's **body** (the same text `forte doc show` prints), so text that
appears only in a processed file's YAML frontmatter is never reported as a match.

### Scenario: A match in a single document

```gherkin
Given a default vault is set
And a document `kickoff.md` has been ingested, whose body contains the line "We agreed the launch date is March 4th." on line 3
When the user runs `forte doc search "launch date"`
Then the process prints a header line `doc #<id>: kickoff.md`
And the process prints an indented line `  line 3: We agreed the launch date is March 4th.`
And the process prints a trailing summary `1 document, 1 match`
And the process exits with status code 0
```

### Scenario: Matches across multiple documents, grouped by document

```gherkin
Given a default vault is set
And a document `kickoff.md` has been ingested whose body mentions "launch date" on lines 3 and 5
And a document `sync.md` has been ingested whose body mentions "launch date" on line 4
When the user runs `forte doc search "launch date"`
Then the process prints a group for `kickoff.md` listing both matching lines, 3 and 5, in ascending order
And the process prints a group for `sync.md` listing its matching line, 4
And a blank line separates the two document groups
And the process prints a trailing summary `2 documents, 3 matches`
And the process exits with status code 0
```

### Scenario: Search is case-insensitive by default

```gherkin
Given a default vault is set
And a document `kickoff.md` has been ingested whose body contains the line "The Launch Date moved."
When the user runs `forte doc search "launch date"`
Then the process reports a match on that line despite the differing case
And the process exits with status code 0
```

### Scenario: `--case-sensitive` restricts matching to exact case

```gherkin
Given a default vault is set
And a document `kickoff.md` has been ingested whose body contains only the line "The Launch Date moved."
When the user runs `forte doc search "launch date" --case-sensitive`
Then the process prints "No matches."
And the process exits with status code 0

When the user instead runs `forte doc search "Launch Date" --case-sensitive`
Then the process reports a match on that line
And the process exits with status code 0
```

### Scenario: The query is treated literally by default

```gherkin
Given a default vault is set
And a document `notes.md` has been ingested whose body contains the line "See section 4.2(a) for details."
When the user runs `forte doc search "4.2(a)"`
Then the process reports a match on that line, treating `.` and `(` as literal characters rather than regex metacharacters
And the process exits with status code 0
```

### Scenario: `--regex` enables regular-expression matching

```gherkin
Given a default vault is set
And a document `notes.md` has been ingested whose body contains the lines "Meeting on 2026-08-11." and "Meeting sometime soon."
When the user runs `forte doc search "\d{4}-\d{2}-\d{2}" --regex`
Then the process reports a match only on the line containing the date, "Meeting on 2026-08-11."
And the process exits with status code 0
```

### Scenario: `--limit` caps matches shown per document

```gherkin
Given a default vault is set
And a document `kickoff.md` has been ingested whose body mentions "launch" on five separate lines
When the user runs `forte doc search "launch" --limit 2`
Then the process prints exactly 2 matching lines under the `kickoff.md` group
And the trailing summary counts only the 2 matches shown, not all 5 occurrences
And the process exits with status code 0
```

### Scenario: No matches found

```gherkin
Given a default vault is set
And a document `kickoff.md` has been ingested whose body does not contain the word "budget"
When the user runs `forte doc search "budget"`
Then the process prints "No matches."
And the process exits with status code 0
```

### Scenario: An empty query is rejected

```gherkin
Given a default vault is set
When the user runs `forte doc search ""`
Then the process prints an error message indicating the search query must not be empty
And the process exits with a non-zero status code
```

### Scenario: An invalid regex is rejected

```gherkin
Given a default vault is set
When the user runs `forte doc search "(unclosed" --regex`
Then the process prints an error message indicating the regular expression is invalid
And the process exits with a non-zero status code
```

### Scenario: Search is scoped to the vault selected by `--vault`

```gherkin
Given a vault named `personal` is the default, containing a document whose body mentions "launch date"
And a vault named `work` is registered, containing no document that mentions "launch date"
When the user runs `forte doc search "launch date" --vault work`
Then the process prints "No matches."
And the process exits with status code 0
And running `forte doc search "launch date"` (using the default vault) still reports the match from `personal`
```

### Scenario: Link a document to an entity

```gherkin
Given a default vault is set
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
Given a default vault is set
And no document with id 99 exists
And an entity with id 3 exists
When the user runs `forte doc link 99 3`
Then the process prints an error message indicating the document was not found
And the process exits with a non-zero status code
And no row is added to the `mentions` table
```

```gherkin
Given a default vault is set
And a document with id 7 exists
And no entity with id 99 exists
When the user runs `forte doc link 7 99`
Then the process prints an error message indicating the entity was not found
And the process exits with a non-zero status code
And no row is added to the `mentions` table
```

### Scenario: Link the same document/entity pair twice is a no-op

```gherkin
Given a default vault is set
And a document with id 7 is already linked to entity id 3
When the user runs `forte doc link 7 3` again
Then the process prints a confirmation message as if the link succeeded
And the process exits with status code 0
And exactly one row linking doc 7 and entity 3 is present in the `mentions` table (no duplicate is created)
```

## `forte doc link-interactive`

`forte doc link-interactive <id>` is the interactive counterpart to `forte doc link`: instead of
looking up an entity's id by hand, the user types a few characters of an entity's name and picks it
from a live-updating suggestion list, in a loop — pick one, it is added to a running list of links,
pick the next, submit an empty line (or Ctrl-D) to finish. Matching is **literal, case-insensitive
substring matching over each entity's name and its aliases** — no LLM, no embeddings, no network
calls — and is deliberately independent of the deferred semantic `entity search` described in
[docs/solution-design.md](./solution-design.md). Suggestions are displayed as `#<id> [<schema>]
<name>`, so the user always sees an entity's id, type, and name before picking it. A successful
session produces exactly the links `forte doc link` would: each picked entity gets a row in the
`mentions` table, `forte doc show <id>` lists it under `Mentions:` afterward, and `forte entity show
<entity_id>` lists the document under its own `Mentions:` section.

### Scenario: Type a partial name and select the suggested entity

```gherkin
Given a default vault is set
And a document with id 12 named "Acme Kickoff Notes" exists
And an entity with id 1, schema `person`, name "Alice" exists
And an entity with id 7, schema `person`, name "Alice Nguyen" exists
When the user runs `forte doc link-interactive 12`
Then the process prints `doc #12: Acme Kickoff Notes`
When the user types `ali`
Then the process shows a suggestion list including `#1 [person] Alice` and `#7 [person] Alice
  Nguyen`, each line showing the entity's id, type, and name
When the user selects `#1 [person] Alice`
Then the process prints a confirmation that `#1 [person] Alice` was linked
When the user finishes the session with an empty line
Then the process prints a summary reporting 1 entity linked to doc #12
And the process exits with status code 0
And a row linking doc 12 and entity 1 is present in the `mentions` table
And running `forte doc show 12` afterward lists `#1 [person] Alice` under `Mentions:`
And running `forte entity show 1` afterward lists document 12 under its `Mentions:` section
```

### Scenario: Select several entities in one session

```gherkin
Given a default vault is set
And a document with id 12 exists
And entities `#1 [person] Alice`, `#4 [client] Acme Corp`, and `#9 [client] Beta LLC` exist
When the user runs `forte doc link-interactive 12`
And the user types `ali` and selects `#1 [person] Alice`
And the user types `acme` and selects `#4 [client] Acme Corp`
And the user finishes the session with an empty line
Then the process reports 2 entities linked, listing `#1 [person] Alice` and `#4 [client] Acme Corp`
And the process exits with status code 0
And rows linking doc 12 to entity 1 and to entity 4 are both present in the `mentions` table
And running `forte doc show 12` afterward lists both entities under `Mentions:`
```

### Scenario: Finishing with an empty line immediately links nothing

```gherkin
Given a default vault is set
And a document with id 12 exists
And at least one entity exists in the vault
When the user runs `forte doc link-interactive 12`
And the user finishes the session immediately with an empty line, without selecting any entity
Then the process prints a message reporting that no entities were linked
And the process exits with status code 0
And no row is added to the `mentions` table for document 12
```

### Scenario: Text that matches no entity re-prompts instead of erroring

```gherkin
Given a default vault is set
And a document with id 12 exists
And an entity with id 1, schema `person`, name "Alice" exists
And no entity's name or alias contains "zzz"
When the user runs `forte doc link-interactive 12`
And the user types `zzz`
Then the process shows no suggestions and a short "no match" message
And the session remains open, still awaiting input, rather than exiting or raising an error
When the user clears the input, types `ali`, and selects `#1 [person] Alice`
And the user finishes the session with an empty line
Then the process reports 1 entity linked, `#1 [person] Alice`
And the process exits with status code 0
```

### Scenario: Selecting an entity already linked to the document is a no-op

```gherkin
Given a default vault is set
And a document with id 12 is already linked to entity `#1 [person] Alice`
When the user runs `forte doc link-interactive 12`
And the user types `ali` and selects `#1 [person] Alice`
Then the process prints a brief message noting the entity is already linked, rather than adding a
  duplicate to the running list
When the user finishes the session with an empty line
Then the process exits with status code 0
And exactly one row linking doc 12 and entity 1 is present in the `mentions` table
```

### Scenario: Aborting mid-session preserves what was already linked

```gherkin
Given a default vault is set
And a document with id 12 exists
And an entity with id 1, schema `person`, name "Alice" exists
When the user runs `forte doc link-interactive 12`
And the user types `ali` and selects `#1 [person] Alice`
And the user aborts the session (Ctrl-C) before finishing
Then the process prints a message reporting that 1 entity was linked before the abort, with no
  Python traceback shown
And the process exits with a non-zero status code
And a row linking doc 12 and entity 1 is present in the `mentions` table
And no further rows are added to the `mentions` table for document 12
```

### Scenario: An unknown document id fails before any prompt is shown

```gherkin
Given a default vault is set
And no document with id 99 exists
When the user runs `forte doc link-interactive 99`
Then the process prints an error message indicating the document was not found
And the process exits with a non-zero status code
And no interactive prompt is shown
And no row is added to the `mentions` table
```

### Scenario: Non-TTY stdin fails fast instead of hanging

```gherkin
Given a default vault is set
And a document with id 12 exists
And stdin is not a TTY (e.g. piped input, or the command is run from a script or agent)
When the user runs `forte doc link-interactive 12`
Then the process prints an error message pointing at `forte doc link <doc_id> <entity_id>` as the
  non-interactive alternative
And the process exits with a non-zero status code
And no interactive prompt is attempted
And no row is added to the `mentions` table
```

### Scenario: A vault with no entities

```gherkin
Given a default vault is set
And a document with id 12 exists
And no entities exist in the vault
When the user runs `forte doc link-interactive 12`
Then the process prints a short message indicating there are no entities to link
And the process exits with status code 0
And no interactive completion menu is shown
```

### Scenario: Unlink a linked document and entity

```gherkin
Given a default vault is set
And a document with id 7 is linked to entity id 3
When the user runs `forte doc unlink 7 3`
Then the process prints a confirmation message naming the document and entity ids
And the process exits with status code 0
And the row linking doc 7 and entity 3 is no longer present in the `mentions` table
And running `forte doc show 7` afterward no longer lists entity id 3 among its linked entities
```

### Scenario: Unlink a pair that is not linked is a no-op

```gherkin
Given a default vault is set
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
Given a default vault is set
And no document with id 99 exists
And an entity with id 3 exists
When the user runs `forte doc unlink 99 3`
Then the process prints an error message indicating the document was not found
And the process exits with a non-zero status code
```

```gherkin
Given a default vault is set
And a document with id 7 exists
And no entity with id 99 exists
When the user runs `forte doc unlink 7 99`
Then the process prints an error message indicating the entity was not found
And the process exits with a non-zero status code
```

### Scenario: Remove an existing document

```gherkin
Given a default vault is set
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
Given a default vault is set
And a document with id 7 is linked to entity id 3
When the user runs `forte doc remove 7 --yes`
Then the process exits with status code 0
And the row linking doc 7 and entity 3 is no longer present in the `mentions` table
And entity id 3 itself still exists in the `entities` table, unmodified
And running `forte entity show 3` afterward still displays entity 3's name, schema, and fields as before
```

### Scenario: Remove a non-existent document

```gherkin
Given a default vault is set
And no document with id 99 exists
When the user runs `forte doc remove 99`
Then the process prints an error message indicating the document was not found
And the process exits with a non-zero status code
And no files are deleted from `docs/raw/` or `docs/processed/`
And no row is removed from the `documents` table
```

### Scenario: Remove without confirmation prompts and aborts

```gherkin
Given a default vault is set
And a document with id 7 exists
When the user runs `forte doc remove 7` and does not confirm the prompt
Then the process prints an "Aborted." message
And the process exits with status code 0
And the document's raw and processed files are still present on disk
And the row for document 7 is still present in the `documents` table
```

### Scenario: The `--yes`/`-y` flag skips the confirmation prompt

```gherkin
Given a default vault is set
And a document with id 7 exists
When the user runs `forte doc remove 7 --yes` (or `forte doc remove 7 -y`)
Then the process does not prompt for confirmation
And the process prints a confirmation message naming the document's id and name
And the process exits with status code 0
And the document is removed as in the "Remove an existing document" scenario
```

### Scenario: Run a doc subcommand with no default vault set and no `--vault`

```gherkin
Given no default vault is registered in `~/.forte/config.yaml`
When the user runs any `forte doc` subcommand (`ingest`, `create`, `list`, `show`, `link`, `link-interactive`, `unlink`, or `remove`) with no `--vault` option
Then the process prints a clear error message telling the user to run `forte vault create` or `forte vault set-default`
And the process exits with a non-zero status code
And no document is ingested, listed, shown, linked, unlinked, or removed
```

### Scenario: Ingest into a non-default vault via `--vault`

```gherkin
Given a vault named `personal` is the default
And a vault named `work` is registered
And a file `kickoff.md` exists on disk outside either vault
When the user runs `forte doc ingest kickoff.md --vault work`
Then the process exits with status code 0
And the vault `work`'s `docs/raw/` and `docs/processed/` directories contain the ingested file's artifacts
And the vault `personal`'s `docs/raw/` and `docs/processed/` directories are unaffected
```

### Scenario: Run a doc subcommand with an unknown `--vault` name

```gherkin
Given no vault named `missing` is registered
When the user runs `forte doc list --vault missing`
Then the process prints an error message indicating the vault was not found
And the process exits with a non-zero status code
```

## `forte doc create` — the follow-on link step

`forte doc create <name>` stores the document first (via the editor step), then — once the
document has an id — offers the same prompt described under `forte doc link-interactive`, so a new
document can be tied to its entities without a separate command. `--no-link` skips that second step
entirely, preserving the fully non-interactive behavior scripts and agents rely on.

### Scenario: `forte doc create` offers the link step after saving

```gherkin
Given a default vault is set
And an entity with id 1, schema `person`, name "Alice" exists
When the user runs `forte doc create "Kickoff Notes"` and saves text in the editor
Then the document is stored and assigned an id, e.g. 12, before any link prompt is shown
And the process then runs the same prompt described under `forte doc link-interactive`
When the user types `ali` and selects `#1 [person] Alice`
And the user finishes the session with an empty line
Then the process prints the created document's id and name, "Kickoff Notes"
And the process prints the entities linked, `#1 [person] Alice`
And the process exits with status code 0
And running `forte doc show 12` afterward lists `#1 [person] Alice` under `Mentions:`
```

### Scenario: `forte doc create --no-link` skips the link step

```gherkin
Given a default vault is set
When the user runs `forte doc create "Kickoff Notes" --no-link` and saves text in the editor
Then the document is stored and assigned an id as usual
And the process does not run the interactive link prompt
And the process exits with status code 0
And no row is added to the `mentions` table for the new document
```

### Scenario: `forte doc create` skips the link step automatically when stdin is not a TTY

```gherkin
Given a default vault is set
And stdin is not a TTY (e.g. the command is run from a script or agent, or with piped input)
When the user runs `forte doc create "Kickoff Notes"`
Then the document is stored and assigned an id as usual
And the process prints a short message noting the link step was skipped because stdin is not
  interactive
And the process exits with status code 0
And no row is added to the `mentions` table for the new document
```

### Scenario: Aborting the link step after `forte doc create` reports progress and a resume hint

```gherkin
Given a default vault is set
And an entity with id 1, schema `person`, name "Alice" exists
When the user runs `forte doc create "Kickoff Notes"` and saves text in the editor
And the user types `ali` and selects `#1 [person] Alice`
And the user aborts the session (Ctrl-C) before finishing
Then the process prints the created document's id, e.g. 12, and reports that 1 entity was linked
  before the abort, with no Python traceback shown
And the process suggests running `forte doc link-interactive 12` to finish linking
And the process exits with a non-zero status code
And the document, and the one link made before the abort, are both still present afterward
```

## `forte doc ingest` — the follow-on link step

`forte doc ingest <path>` stores the document first (copy + extract, as in the ingest scenarios
above), then — once the document has an id — offers the same prompt described under `forte doc
link-interactive`. `--no-link` skips that second step. A deduped re-ingest (see "Re-ingest an
unchanged file is a no-op" above) still offers the link step, against the existing document's id,
rather than skipping it.

### Scenario: `forte doc ingest` offers the link step after storing the document

```gherkin
Given a default vault is set
And a file `kickoff.md` exists on disk outside the vault
And an entity with id 1, schema `person`, name "Alice" exists
When the user runs `forte doc ingest kickoff.md`
Then the document is copied, extracted, and assigned an id, e.g. 12, before any link prompt is shown
And the process then runs the same prompt described under `forte doc link-interactive`
When the user types `ali` and selects `#1 [person] Alice`
And the user finishes the session with an empty line
Then the process prints the ingested document's id and name
And the process prints the entities linked, `#1 [person] Alice`
And the process exits with status code 0
And running `forte doc show 12` afterward lists `#1 [person] Alice` under `Mentions:`
```

### Scenario: `forte doc ingest --no-link` skips the link step

```gherkin
Given a default vault is set
And a file `kickoff.md` exists on disk outside the vault
When the user runs `forte doc ingest kickoff.md --no-link`
Then the document is copied, extracted, and assigned an id as usual
And the process does not run the interactive link prompt
And the process exits with status code 0
And no row is added to the `mentions` table for the new document
```

### Scenario: `forte doc ingest` skips the link step automatically when stdin is not a TTY

```gherkin
Given a default vault is set
And a file `kickoff.md` exists on disk outside the vault
And stdin is not a TTY (e.g. the command is run from a script or agent, or with piped input)
When the user runs `forte doc ingest kickoff.md`
Then the document is copied, extracted, and assigned an id as usual
And the process prints a short message noting the link step was skipped because stdin is not
  interactive
And the process exits with status code 0
And no row is added to the `mentions` table for the new document
```

### Scenario: A deduped re-ingest still offers the link step

```gherkin
Given a default vault is set
And `forte doc ingest kickoff.md` has already been run successfully, assigning it id 7
And the file at `kickoff.md` has not changed since (same source path and same content hash)
And an entity with id 1, schema `person`, name "Alice" exists
When the user runs `forte doc ingest kickoff.md` again
Then the process reports the existing document id 7 rather than creating a new one
And the process then runs the same prompt described under `forte doc link-interactive`, against
  document id 7
When the user types `ali` and selects `#1 [person] Alice`
And the user finishes the session with an empty line
Then the process exits with status code 0
And running `forte doc show 7` afterward lists `#1 [person] Alice` under `Mentions:`
```

### Scenario: Aborting the link step after `forte doc ingest` reports progress and a resume hint

```gherkin
Given a default vault is set
And a file `kickoff.md` exists on disk outside the vault
And an entity with id 1, schema `person`, name "Alice" exists
When the user runs `forte doc ingest kickoff.md`
And the user types `ali` and selects `#1 [person] Alice`
And the user aborts the session (Ctrl-C) before finishing
Then the process prints the ingested document's id, e.g. 12, and reports that 1 entity was linked
  before the abort, with no Python traceback shown
And the process suggests running `forte doc link-interactive 12` to finish linking
And the process exits with a non-zero status code
And the document, and the one link made before the abort, are both still present afterward
```

## Out of scope

- **Entity extraction from doc content** — no LLM call inspects a document's text to propose entities or field values in this batch.
- **Entity linking proposals** — `mentions` rows are only created/removed directly, by a human choosing an id (`doc link`/`doc unlink`) or picking from a substring-matched suggestion list (`doc link-interactive`); there is no automatic, LLM-driven proposal step.
- **Field extraction** — no extraction of structured field values from documents.
- **The review TUI** — there is nothing to approve yet, so no interactive review flow exists for docs.
- **`ingest_changes` / resumable ingest** — this batch's `ingest` is a single atomic step (copy + extract + record), not a multi-step pipeline with persisted intermediate proposals.
- **`--yes` auto-approve flag** — not applicable since there is no proposal step to approve.
- **`doc show` displaying full entity details** — it lists linked entity ids only; richer display (entity name, schema, fields) is deferred.
- **OCR, audio, web, and email ingestion** — `doc ingest` only supports `.md`, `.txt`, `.docx`, and `.pdf` in this batch.

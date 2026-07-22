# `forte agent` Spec

Behavior spec for the `forte agent` command group — `forte agent process` and `forte agent ingest` — which run the LLM-driven pipeline that turns an ingested document into proposed entities, links, and field values, walks the user through reviewing each proposal, and commits the approved ones to the knowledge base. `agent process <doc-id>` runs the pipeline (extract entities → review → link/create entities → review → extract structured fields → review → commit) against a document that has already been ingested via `forte doc ingest`. `agent ingest <path>` is a convenience wrapper that runs `forte doc ingest` and then `forte agent process` in one command. All pipeline state (candidates, proposed changes, approve/reject decisions) is held **in memory** for the duration of the run; nothing is written to markdown or SQLite until the final commit step, and every scenario below runs against a **stubbed LLM boundary** — deterministic, scripted responses with zero cost — never a live model. These commands operate on an existing vault, discovered git-style by walking up from the current working directory to find a `.forte/` directory.

## Scenarios

### Scenario: Walk through proposed entities, links, and fields one at a time

```gherkin
Given the current working directory is inside a Forte vault
And a `person` schema exists with fields `employer` and `role`
And a document has been ingested with id 7, whose text mentions a new person "Ada Lovelace"
And the LLM is stubbed to extract one candidate entity `Ada Lovelace` (schema `person`) with a supporting quote
And the LLM is stubbed to propose no rule-matched link for that candidate, so it resolves to a new-entity proposal
And the LLM is stubbed to extract field values `role=Mathematician` for the approved entity
When the user runs `forte agent process 7` and approves each proposed change as it is presented
Then the process presents the candidate entity proposal first, then the link/create proposal, then the field-set proposal, one at a time
And the process exits with status code 0
And a markdown file for `Ada Lovelace` exists under `entities/person/`
And a row for the entity is present in the `entities` table
And a row linking document 7 to the new entity is present in the `mentions` table
And running `forte entity show <id>` afterward shows `role` set to `Mathematician`
```

### Scenario: Rejected proposals are not written

```gherkin
Given the current working directory is inside a Forte vault
And a `person` schema exists
And a document has been ingested with id 7
And the LLM is stubbed to extract one candidate entity `Ada Lovelace` (schema `person`) that resolves to a new-entity proposal
When the user runs `forte agent process 7` and rejects the new-entity proposal
Then the process exits with status code 0
And no markdown file for `Ada Lovelace` exists under `entities/person/`
And no row for `Ada Lovelace` is present in the `entities` table
And no row is added to the `mentions` table for document 7
```

### Scenario: `--yes` auto-approves everything non-interactively

```gherkin
Given the current working directory is inside a Forte vault
And a `person` schema exists with fields `employer` and `role`
And a document has been ingested with id 7
And the LLM is stubbed to extract a candidate entity, resolve it as new, and extract a field value for it
When the user runs `forte agent process 7 --yes`
Then the process does not prompt for confirmation at any stage
And the process prints a summary of the changes committed
And the process exits with status code 0
And a markdown file for the new entity exists under `entities/person/`
And a row for the entity and a row in `mentions` linking it to document 7 are both present
```

### Scenario: `--dry-run` writes nothing

```gherkin
Given the current working directory is inside a Forte vault
And a `person` schema exists
And a document has been ingested with id 7
And the LLM is stubbed to extract a candidate entity, resolve it as new, and extract a field value for it
When the user runs `forte agent process 7 --dry-run` (with or without `--yes`)
Then the process proposes and (per the chosen presentation) may display each stage's changes
And the commit step is skipped entirely
And the process exits with status code 0
And no markdown file is created under `entities/`
And no row is added to the `entities` table
And no row is added to the `mentions` table
And running `forte entity list` afterward shows no new entity
And running `forte doc show 7` afterward shows no newly linked entity
```

### Scenario: Process a non-existent document id

```gherkin
Given the current working directory is inside a Forte vault
And no document with id 99 exists
When the user runs `forte agent process 99`
Then the process prints an error message indicating the document was not found
And the process exits with a non-zero status code
And no entity, mention, or markdown file is created
And no LLM call is made
```

### Scenario: A step's LLM call exhausts all retries and the run aborts with nothing committed

```gherkin
Given the current working directory is inside a Forte vault
And a `person` schema exists
And a document has been ingested with id 7
And the LLM is stubbed to return malformed/schema-invalid JSON for the extract-entities step on every attempt, for all 5 retries
When the user runs `forte agent process 7 --yes`
Then the process prints an error message indicating the step failed after exhausting retries
And the process exits with a non-zero status code
And no new row is present in the `entities` table
And no new row is present in the `mentions` table
And no new markdown file is created under `entities/`
```

### Scenario: A step returning zero results skips cleanly to done

```gherkin
Given the current working directory is inside a Forte vault
And a document has been ingested with id 7
And the LLM is stubbed so the extract-entities step returns zero candidates
When the user runs `forte agent process 7 --yes`
Then the process does not attempt a link/create or field-extraction stage
And the process prints a summary indicating nothing was found to propose
And the process exits with status code 0
And no row is added to the `entities` or `mentions` tables
```

### Scenario: A candidate matching an existing entity is proposed as a link, not a duplicate

```gherkin
Given the current working directory is inside a Forte vault
And an entity `Ada Lovelace` (schema `person`) already exists with id 3, with alias `Ada`
And a document has been ingested with id 7, whose text mentions "Ada"
And the LLM is stubbed to extract a candidate named `Ada` (schema `person`)
And the rule-based matcher finds entity id 3 via the alias match
And the LLM is stubbed to pick entity id 3 as the link target, with a supporting quote
When the user runs `forte agent process 7` and approves the proposed link
Then the process presents the proposal as a link to the existing entity `Ada Lovelace` (id 3), not a new entity
And the process exits with status code 0
And a new row linking document 7 and entity 3 is present in the `mentions` table
And no new row is added to the `entities` table
And no second markdown file is created under `entities/person/`
```

### Scenario: A candidate with no rule match is proposed as a new entity

```gherkin
Given the current working directory is inside a Forte vault
And no existing entity's name, alias, or normalized name matches "Grace Hopper"
And a document has been ingested with id 7, whose text mentions "Grace Hopper"
And the LLM is stubbed to extract a candidate named `Grace Hopper` (schema `person`)
When the user runs `forte agent process 7` and approves the proposal
Then the rule-based matcher returns no candidate entities, so no link-resolution LLM call is made for this candidate
And the process presents the proposal as a new entity
And the process exits with status code 0
And a markdown file for `Grace Hopper` is created under `entities/person/`
And a new row is present in the `entities` table
```

### Scenario: An approved link persists the LLM's supporting quote

```gherkin
Given the current working directory is inside a Forte vault
And an entity `Ada Lovelace` exists with id 3
And a document has been ingested with id 7
And the LLM is stubbed to propose a link to entity 3 with supporting quote "Ada Lovelace wrote the first algorithm"
When the user runs `forte agent process 7 --yes`
Then the process exits with status code 0
And the new row in the `mentions` table linking document 7 and entity 3 has its `quote` column set to "Ada Lovelace wrote the first algorithm"
```

### Scenario: Field extraction only fills empty fields, never overwrites existing values

```gherkin
Given the current working directory is inside a Forte vault
And an entity `Ada Lovelace` (schema `person`, fields `employer` and `role`) exists with id 3
And `employer` is already set to "Analytical Engine Co." and `role` is empty
And a document has been ingested with id 7 that links to entity 3 during this run
And the LLM is stubbed to extract field values `employer=Somewhere Else` and `role=Mathematician` for entity 3
When the user runs `forte agent process 7 --yes`
Then the process exits with status code 0
And running `forte entity show 3` afterward shows `employer` still set to "Analytical Engine Co." (not overwritten)
And running `forte entity show 3` afterward shows `role` set to "Mathematician" (the previously empty field was filled)
```

### Scenario: `agent ingest` ingests a file and processes it in one command

```gherkin
Given the current working directory is inside a Forte vault
And a file `kickoff.md` exists on disk outside the vault
And the LLM is stubbed to extract a candidate entity, resolve it as new, and extract a field value for it
When the user runs `forte agent ingest kickoff.md --yes`
Then the process ingests `kickoff.md` as it would via `forte doc ingest`, assigning it a document id
And the process then runs the same extract/link/field pipeline as `forte agent process` against that document id
And the process prints a summary of the changes committed
And the process exits with status code 0
And a row for the document is present in the `documents` table
And a markdown file for the new entity exists under `entities/`, with a `mentions` row linking it to the ingested document
```

### Scenario: `agent ingest --dry-run` ingests the file but writes no entities or mentions

```gherkin
Given the current working directory is inside a Forte vault
And a file `kickoff.md` exists on disk outside the vault
And the LLM is stubbed to extract a candidate entity that resolves to a new-entity proposal
When the user runs `forte agent ingest kickoff.md --dry-run`
Then the process exits with status code 0
And a row for the document is present in the `documents` table (the mechanical ingest step is not part of the dry-run)
And no row is added to the `entities` table
And no row is added to the `mentions` table
```

### Scenario: A completed run prints a cost/usage summary

```gherkin
Given the current working directory is inside a Forte vault
And a document has been ingested with id 7
And the LLM is stubbed to return known token-usage figures for each call it services during the run
When the user runs `forte agent process 7 --yes`
Then the process exits with status code 0
And the process prints a summary line reporting total input tokens, output tokens, and an estimated cost for the run
And the summary is clearly labeled as an estimate
```

### Scenario: Run an agent subcommand outside a vault

```gherkin
Given the current working directory is not inside a Forte vault
And no `.forte/` directory exists in the current directory or any ancestor
When the user runs any `forte agent` subcommand (`process` or `ingest`)
Then the process prints an error message indicating the user is not inside a Forte vault
And the process exits with a non-zero status code
And no document, entity, or mention is created, modified, or removed
And no LLM call is made
```

## Out of scope

- **`ingest_changes` persistence / resumable resume** — all pipeline state (candidates, proposals, decisions) is held in memory only; a Ctrl-C or crash mid-run loses in-flight progress with nothing committed. There is no persisted, resumable multi-step ingest state.
- **Embeddings / vector candidate discovery / `forte entity search`** — entity linking uses only rule-based matching (exact name, exact alias, normalized name/alias); semantic or vector-based candidate discovery is not built.
- **Per-vault prompt overrides** — the extraction/link/field prompts live in source code for this batch; no mechanism exists yet to override them per vault.
- **Per-step model overrides** — a single model is used for every step in a run; there is no way to configure a different model per pipeline step.
- **Field-value provenance (`entity_field_values`)** — field values land in the entity's `fields_json` via the normal entity-edit path; the `entity_field_values` table is not populated, so which document/quote produced a given field value is not tracked.
- **Inline editing of proposed changes** — the review flow offers approve or reject only; there is no way to edit a proposed name, field value, or link target before approving it. Corrections happen afterward via `forte entity edit`.
- **Batch/folder processing** — `agent process` and `agent ingest` operate on exactly one document per invocation; there is no flag to process a folder or multiple documents in one run.
- **Live-model evaluation** — every scenario above runs against a stubbed LLM boundary for determinism and zero cost. Any live-model "eval" tests assessing real prompt quality are kept out of the main automated suite.

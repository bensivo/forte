# `forte agent` Bulk (default) Review Flow Spec

> **File choice:** these scenarios live in a sibling file, `docs/spec/forte-agent-bulk-commit.md`, rather than appended to `docs/spec/forte-agent.md`, to keep the base agent spec focused on the one-at-a-time `--interactive` review flow. This file assumes familiarity with `docs/spec/forte-agent.md` (vault discovery, the stubbed-LLM convention, the pipeline stages) and only specifies what the bulk flow changes.

Behavior spec for the **default** review flow on `forte agent process` and `forte agent ingest`. When neither `--yes` nor `--interactive`/`-i` is given, the agent uses the bulk editor. Instead of walking the user through each proposed change one at a time across two separate review points (entities/links, then fields — the `--interactive` flow described in `docs/spec/forte-agent.md`), the bulk flow collapses **both** review points into a **single editor session**: every proposed new entity, every proposed link, and every proposed field update (eagerly extracted for all proposed entities, not just ones the user has approved yet) is written into one text file, organized into three sections, each line pre-filled with a `[y]` action. The file is handed to an editor; whatever comes back is parsed into approve/reject decisions and committed in one pass.

Flag precedence: `--yes` beats everything (auto-approve, no editor, no prompts); otherwise `--interactive`/`-i` selects the one-at-a-time flow; otherwise this bulk flow is the default. `--dry-run` composes with all three.

Every scenario below runs against a **stubbed LLM boundary** (deterministic, scripted responses, zero cost — see `docs/spec/forte-agent.md`) **and** a **stubbed editor boundary**: the editor-session seam is a function `str -> str` (or one that raises `EditorAbortedError`) that tests script directly. No scenario ever spawns a real editor process or a real `$EDITOR`/`$VISUAL` program.

## Scenarios

### Scenario: All proposals are presented in one editor pass, unlike the `--interactive` flow's two review points

```gherkin
Given the current working directory is inside a Forte vault
And a `person` schema exists with fields `employer` and `role`
And a `project` schema exists
And a document has been ingested with id 7
And the LLM is stubbed to extract candidates that resolve to: one new-entity proposal (`person` "Alice"), one link proposal to an existing `project` entity, and field values for both the new entity and the linked entity
When the user runs `forte agent process 7`
Then exactly one call is made to the (stubbed) editor boundary, unlike the `--interactive` flow's separate entity-review and field-review prompts
And the text handed to the editor contains all three proposals: the new entity, the link, and both field updates
And the text is organized into three sections in order: new entities, links to existing entities, field updates
And every proposal line is pre-filled with the `[y]` action
```

### Scenario: Unchanged editor return approves every proposal

```gherkin
Given the setup from "All proposals are presented in one editor pass"
And the stubbed editor returns the file contents unchanged
When the user runs `forte agent process 7`
Then the process exits with status code 0
And a markdown file for the new entity `Alice` exists under `entities/person/`
And a row for the new entity is present in the `entities` table
And a row linking document 7 to the new entity is present in the `mentions` table
And a row linking document 7 to the existing linked entity is present in the `mentions` table
And running `forte entity show` for both entities afterward shows the extracted field values applied
```

### Scenario: Flipping lines to `[n]` skips only those proposals

```gherkin
Given the setup from "All proposals are presented in one editor pass"
And the stubbed editor flips the new-entity line's action from `[y]` to `[n]`, and flips one field-update line's action from `[y]` to `[n]`, leaving all other lines as `[y]`
When the user runs `forte agent process 7`
Then the process exits with status code 0
And no markdown file for the new entity `Alice` exists under `entities/person/`
And no row for the new entity `Alice` is present in the `entities` table
And no row is added to the `mentions` table for document 7 and the rejected new entity
And the field values from the rejected field-update line are not applied to their target entity
And the proposals still marked `[y]` (the link, and the other field update) are committed as normal
```

### Scenario: Deleting a proposal line is treated as skipping it

```gherkin
Given the setup from "All proposals are presented in one editor pass"
And the stubbed editor deletes the link proposal's line from the file entirely (rather than changing its action token)
When the user runs `forte agent process 7`
Then the process exits with status code 0
And no row linking document 7 to the linked entity is added to the `mentions` table
And this has the same observable effect as if that line had been flipped to `[n]`
And the other proposals in the file (still `[y]`) are committed as normal
```

### Scenario: An unrecognized or blank action token is treated as skipping the line

```gherkin
Given the setup from "All proposals are presented in one editor pass"
And the stubbed editor rewrites the new-entity line's action token to `[x]` (an unrecognized token)
And the stubbed editor rewrites one field-update line's action token to an empty `[ ]`
When the user runs `forte agent process 7`
Then the process exits with status code 0
And neither the new entity with the garbage action token nor the field update with the blank action token is committed
And this has the same observable effect as `[n]`
```

### Scenario: Edge case — approving a field-set on a skipped new entity creates the entity anyway

```gherkin
Given the current working directory is inside a Forte vault
And a `person` schema exists with field `role`
And a document has been ingested with id 7
And the LLM is stubbed to extract one candidate that resolves to a new-entity proposal for `person` "Grace Hopper" (no rule-based link match), plus a field update proposing `role=Rear Admiral` targeting that same new entity
When the user runs `forte agent process 7`
And the stubbed editor sets `[n]` on the new-entity line for "Grace Hopper" but leaves `[y]` on the field-update line targeting "Grace Hopper"
Then the process exits with status code 0
And a markdown file for "Grace Hopper" is created under `entities/person/`
And a row for "Grace Hopper" is present in the `entities` table
And a row linking document 7 to the "Grace Hopper" entity is present in the `mentions` table
And running `forte entity show` for the new entity afterward shows `role` set to "Rear Admiral"
```

### Scenario: Renaming a proposed new entity creates it under the edited name

```gherkin
Given the current working directory is inside a Forte vault
And a `person` schema exists with field `role`
And a document has been ingested with id 7
And the LLM is stubbed to extract one candidate that resolves to a new-entity proposal for `person` "Ada" (no rule-based link match), plus a field update proposing `role=Mathematician` targeting that same new entity
When the user runs `forte agent process 7`
And the stubbed editor edits the new-entity line's name from "Ada" to "Ada Lovelace" and leaves every action as `[y]`
Then the process exits with status code 0
And a markdown file for "Ada Lovelace" is created under `entities/person/`
And a row for "Ada Lovelace" (not "Ada") is present in the `entities` table
And running `forte entity show` for the new entity afterward shows `role` set to "Mathematician" (the field update followed the renamed entity)
And no entity named "Ada" is created
```

### Scenario: A renamed new entity that is skipped but promoted is created under the edited name

```gherkin
Given the current working directory is inside a Forte vault
And a `person` schema exists with field `role`
And a document has been ingested with id 7
And the LLM is stubbed to extract one candidate that resolves to a new-entity proposal for `person` "Ada", plus a field update proposing `role=Mathematician` targeting that same new entity
When the user runs `forte agent process 7`
And the stubbed editor renames the new-entity line from "Ada" to "Ada Lovelace" AND sets its action to `[n]`, but leaves the field-update line as `[y]`
Then the process exits with status code 0
And the entity is created anyway (promotion) under the edited name "Ada Lovelace"
And running `forte entity show` for it afterward shows `role` set to "Mathematician"
```

### Scenario: `--yes` overrides the default bulk flow — no editor is invoked

```gherkin
Given the current working directory is inside a Forte vault
And a `person` schema exists
And a document has been ingested with id 7
And the LLM is stubbed to extract a candidate entity, resolve it as new, and extract a field value for it
When the user runs `forte agent process 7 --yes`
Then the stubbed editor boundary is never invoked
And every proposal (the new entity and its field update) is auto-approved and committed, exactly as `--yes` behaves in the default flow
And the process exits with status code 0
And a markdown file for the new entity exists under `entities/person/`
And a row for the entity and a row in `mentions` linking it to document 7 are both present
```

### Scenario: `--dry-run` with the default bulk flow — editor runs, nothing is committed

```gherkin
Given the current working directory is inside a Forte vault
And a `person` schema exists
And a document has been ingested with id 7
And the LLM is stubbed to extract a candidate entity, resolve it as new, and extract a field value for it
And the stubbed editor returns the file contents unchanged (all `[y]`)
When the user runs `forte agent process 7 --dry-run`
Then the stubbed editor boundary is invoked and decisions are collected from its return value
And the commit step is skipped entirely
And the process exits with status code 0
And no markdown file is created under `entities/`
And no row is added to the `entities` table
And no row is added to the `mentions` table
```

### Scenario: Editor abort — nothing is committed and the run fails clearly

```gherkin
Given the current working directory is inside a Forte vault
And a `person` schema exists
And a document has been ingested with id 7
And the LLM is stubbed to extract a candidate entity, resolve it as new, and extract a field value for it
And the stubbed editor boundary is scripted to raise `EditorAbortedError` (simulating a launcher reporting the editor process exited non-zero, e.g. the user ran `:cq` in vim)
When the user runs `forte agent process 7`
Then the process prints a clear error message indicating the editor was aborted and nothing was committed
And the process exits with a non-zero status code
And no markdown file is created under `entities/`
And no row is added to the `entities` table
And no row is added to the `mentions` table
```

### Scenario: Zero proposals — the editor is never opened

```gherkin
Given the current working directory is inside a Forte vault
And a document has been ingested with id 7
And the LLM is stubbed so the extract-entities step returns zero candidates
When the user runs `forte agent process 7`
Then the stubbed editor boundary is never invoked
And the process prints a summary indicating there was nothing to propose
And the process exits with status code 0
And no row is added to the `entities` or `mentions` tables
```

### Scenario: `agent ingest` (default bulk flow) end-to-end

```gherkin
Given the current working directory is inside a Forte vault
And a `person` schema exists with field `role`
And a file `kickoff.md` exists on disk outside the vault, whose text mentions a new person "Ada Lovelace"
And the LLM is stubbed to extract a candidate entity, resolve it as new, and extract a field value for it
And the stubbed editor returns the file contents unchanged (all `[y]`)
When the user runs `forte agent ingest kickoff.md`
Then the process ingests `kickoff.md` as it would via `forte doc ingest`, assigning it a document id
And a row for the document is present in the `documents` table
And the same bulk flow described above then runs against that document id, invoking the stubbed editor exactly once
And the process exits with status code 0
And a markdown file for the new entity exists under `entities/person/`, with a `mentions` row linking it to the ingested document
```

## Out of scope

- **Everything already out of scope for the base agent flow** — see `docs/spec/forte-agent.md`'s `## Out of scope` section (`ingest_changes` persistence/resume, embeddings/vector candidate discovery, per-vault prompt overrides, per-step model overrides, field-value provenance, batch/folder processing, live-model evaluation). All of that applies unchanged to the default bulk flow.
- **Creating brand-new entities by typing lines in the editor** — the user can only accept (`[y]`) or skip (`[n]`/delete/garbage) proposals the pipeline already generated; there is no way to add an entity that wasn't proposed by editing the file.
- **Converting a proposal's type (new ↔ link) in the editor** — a line proposed as a new entity cannot be turned into a link to an existing entity (or vice versa) by editing the file; that requires rejecting the proposal and using the normal entity-linking tools afterward.
- **Per-line inline field editing** — field-update lines show the proposed key/value pairs for approval or rejection as a whole; there is no way to edit an individual field's proposed value inside the editor.
- **Re-opening the editor to fix mistakes** — there is no "reopen and correct" flow; if the user saves a bad edit (e.g. wrong line deleted), the fix is to re-run the command from scratch, not to resume editing the same session.

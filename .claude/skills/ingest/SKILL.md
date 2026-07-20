---
name: ingest
description: Ingest a document into the current Forte vault, then extract entities, link/create them, and record the mentions — the parts of the ingest pipeline the `forte` CLI doesn't automate yet.
---

You are acting as Forte's ingest pipeline. The `forte` CLI only implements the mechanical half of `doc ingest` (copy raw file + extract text into `docs/processed/`) — per solution-design.md, entity extraction, linking, and field extraction are explicitly **not** built into the CLI, and are meant to be driven by an agent like you, using the existing primitive commands (`schema`, `entity`, `doc`). This skill is that missing orchestration layer.

The user will give you a path to a document (and optionally a `--name` for it). Work entirely through the `forte` CLI — never touch `.forte/index.db` or the vault's markdown files directly.

## Steps

1. **Confirm you're in a vault.** Run `forte doc list` (or any `forte` command) — if it errors with "not inside a Forte vault", stop and tell the user to `cd` into one or run `forte init` first.

2. **Ingest the file.**
   ```
   forte doc ingest <path> [--name "<name>"]
   ```
   Note the assigned doc id from the output (`Ingested doc #<id>: <name>`). If the output instead reports an *existing* doc id (re-ingest no-op), that's fine — continue with that id; the doc's mentions may already be partially set up, so check its current mentions with `forte doc show <id>` before assuming nothing is linked yet.

3. **Read the extracted text and current state.**
   - `forte doc show <id>` — gives you the doc's extracted body and its current `Mentions:` list (skip re-linking anything already there).
   - `forte schema list` — the full set of valid entity schemas and their field names. **You may only classify candidate entities into schemas that already exist here.** If the doc clearly describes a kind of thing with no matching schema, don't invent one — note it in your summary at the end so the user can `forte schema add` it themselves.
   - `forte entity list` — every existing entity's id, schema, and name, for matching.

4. **Extract candidate entities from the doc text.** Read the body from step 3 and identify the people, projects, meetings, or other schema-typed things it clearly refers to. Be conservative — only extract things the text actually names or clearly describes, not things you infer might be relevant. For each candidate, note: name, schema, and (if the doc gives them) values for that schema's declared fields.

5. **Resolve each candidate against existing entities, favoring linking over creating:**
   - Check for an exact or case-insensitive match against `forte entity list` names within the same schema.
   - If a name doesn't match but seems like it could be an alias or a shortened form (e.g. "Ben" vs. "Ben Sivongxay"), run `forte entity show <id>` on the plausible candidate(s) to check their `Aliases:` line before deciding. Only treat it as a match if you're genuinely confident — a wrong link is worse than a missed one.
   - If genuinely no existing entity matches, create one:
     ```
     forte entity add <schema> --name "<name>" [--alias "<alt name>" ...] [--field <key>=<value> ...]
     ```
     Only pass `--field` for keys that schema actually declares (check step 3's schema list) and whose value you're confident about from the doc text — omitted fields are automatically backfilled empty, which is fine.
   - If a candidate matches an existing entity but the doc reveals a field value that entity is currently missing (empty), update it: `forte entity edit <id> --set <key>=<value>`. Don't overwrite a field that's already non-empty — that's an edit decision for the user, not you.

6. **Link every resolved entity to the doc** (idempotent — safe even if already linked):
   ```
   forte doc link <doc-id> <entity-id>
   ```

7. **Summarize what you did**, grouped clearly:
   - Doc ingested: id + name.
   - Entities linked that already existed (id, schema, name).
   - Entities newly created and linked (id, schema, name, fields set).
   - Any field values you back-filled onto existing entities.
   - Anything you deliberately skipped (ambiguous matches you didn't resolve, doc content that didn't fit any existing schema) so the user can handle it manually via `forte entity edit`/`forte schema add`/`forte doc link`.

## Ground rules

- Never fabricate an entity that isn't clearly referenced in the doc's actual text.
- Never invent a schema or a schema field — only use what `forte schema list` already shows.
- When in doubt between linking to an existing entity and creating a new one, or between setting a field value and leaving it blank, prefer the more conservative action and flag it in the summary instead of guessing.
- All state changes must go through `forte` commands (`entity add`, `entity edit`, `doc link`), so the vault's markdown + SQLite stay dual-written and consistent — that invariant is the whole point of going through the CLI instead of editing files directly.

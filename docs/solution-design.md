# Solution Design - V0

This document describes *how* Forte's MVP will be built. Requirements live in [prd.md](./prd.md); this doc translates them into a concrete design.

## Overview

Forte is a single-binary Python CLI that operates on a local vault directory. A vault holds three kinds of state:

1. **Markdown files** on disk — the human-readable source of truth for raw docs, processed docs, and entities.
2. **SQLite index** (`.forte/index.db`) — the queryable representation of the same data, used for fast lookups, filtering, and semantic search.
3. **Config** (`.forte/config.yaml`) — model choice, API keys, operational settings.

Both the markdown files and SQLite index are authoritative. Every write operation updates both; the CLI does not attempt to reconcile drift between them at MVP.

The CLI is composed of small primitive commands. Higher-level orchestration (e.g., "ingest all new docs in this folder, then summarize") is expected to be driven externally — by the user, by shell scripts, or by an agent like Claude Code — in the MVP. A dedicated orchestration layer is a future phase, likely built on **LangGraph**.

### Architecture layers

The code is organized in four layers, each depending only on the ones below it:

1. **Driver / controller layer** — Click commands and Rich prompts. Handles CLI
   input/output and the interactive approve/reject flow.
2. **Service layer** — ingest pipeline orchestration, entity extraction, and
   entity-linking logic. Owns the multi-step, resumable ingest flow.
3. **DB layer** — the markdown + SQLite dual-write repositories.
4. **Domain layer** — core models (Entity, Schema, Document, Mention) and business
   rules such as the schema-field invariant.

### Delivery context

Forte's MVP is built by a **solo developer over a few weekends**, with **AI agents doing
much of the coding** once this spec is locked. This favors a tight, well-specified scope
and clear invariants over breadth.

## Tech Stack

- **Language / runtime:** Python 3.11+
- **Packaging / tooling:** `uv` (dependency management, virtualenv, and distribution)
- **CLI framework:** Click
- **TUI:** Rich prompts (`Confirm.ask` / `Prompt.ask`) — the review flow is inherently
  sequential (one change at a time), so it does not need Textual's app/event loop. Textual
  is a possible future upgrade if a scrollable, multi-pane review dashboard is wanted.
- **LLM:** Anthropic Python SDK, defaulting to `claude-haiku-4-5`
- **Embeddings:** **Deferred.** The provider choice — local `sentence-transformers` vs. a
  hosted API (e.g. Voyage AI, which Anthropic recommends; Anthropic ships no first-party
  embeddings API) — will be settled by a spike comparing performance, ease of use, and
  cost. Semantic `entity search` depends on this and is deferred with it.
- **Storage:** SQLite via `sqlite3` stdlib; `sqlite-vec` or similar for vector column
  (once embeddings are chosen)
- **Doc parsing:** `python-markdown`, `python-docx`, `pypdf` for text-only extraction
- **Distribution:** `uv`-based for now (`uv tool install`); revisit the user-facing
  install path later.

## Vault Folder Structure

```
my-vault/
  .forte/
    index.db              SQLite index of docs, entities, links, embeddings
    config.yaml           Model choice, API keys, operational settings
  docs/
    raw/                  Copies of original ingested source documents (immutable)
    processed/            Post-extraction markdown, linked back to raw originals
  entities/
    person/               One markdown file per Person entity
    project/              One markdown file per Project entity
    <schema>/             One folder per user-defined schema
```

### File conventions

- **Entity files** use YAML frontmatter for structured fields and a free-form markdown
  body for notes. Frontmatter always carries two built-in fields — a **required `name`**
  and an **`aliases`** list — plus the user-defined fields of the entity's schema. `name`
  and `aliases` are structural (present on every entity regardless of schema); they are
  *not* schema-defined fields.
- **Processed docs** contain the verbatim text of the original document plus YAML
  frontmatter. The frontmatter links back to the raw source file and lists the IDs of the
  entities mentioned in the doc. Mentions are a flat list in frontmatter — there is no
  inline markup in the body.
- Filenames are slugified from the canonical entity name (`person/ben-sivongxay.md`) so
  users can find them by browsing.

### IDs

Entities and documents are identified by **auto-increment integers** assigned by SQLite
(`forte entity show 42`). IDs are stable across renames.

### Schemas

- A schema is a named entity kind plus an ordered list of **field names**. Fields are
  **free-text** at MVP — no per-field types and no value validation (all values are
  optional and may be empty).
- **Structural validation is enforced**, however: every entity of a schema must carry
  *exactly* that schema's field set. No field may be missing (empty is fine) and no field
  outside the schema may appear. (`name`/`aliases` are exempt — they are built-in.)
- Fields are declared with repeated `--field` flags (`forte schema add role
  --field company --field title`). More granular commands like
  `forte schema add-field` / `remove-field` are anticipated as follow-ups.
- **Schema mutations cascade automatically** to preserve the invariant: adding a field
  back-fills every existing entity of that schema with an empty value; removing a field
  strips it from every existing entity. No manual migration step.

## CLI Spec

```
forte init                              Create a new vault in the current directory

forte schema add <name>                 Define a new schema (entity kind) and its fields
forte schema list                       List all schemas in the vault
forte schema remove <name>              Remove a schema

forte entity add <schema>               Manually create a new entity of the given schema
forte entity list [--schema <schema>]     List entities, optionally filtered by schema
forte entity show <id>                  Show an entity's fields and linked docs
forte entity edit <id>                  Edit an entity's fields and aliases
forte entity remove <id>                Remove an entity
forte entity search <query>             Semantic search over entity names, aliases, content

forte doc ingest <path> [--yes]         Ingest a document; --yes auto-approves all changes
forte doc list                          List ingested documents
forte doc show <id>                     Show a document's contents and extracted entities
```

Vault discovery is git-style: each command walks up from CWD looking for a `.forte/` directory.

## SQLite Schema (draft)

- `documents(id, source_path, content_hash, raw_path, processed_path, ingested_at, status)`
  — `source_path` + `content_hash` together form the **ingest identity** (see Ingest
  Pipeline).
- `schemas(name, fields_json)`
- `entities(id, schema, name, aliases_json, fields_json, file_path)`
- `entity_field_values(entity_id, field, value, source_doc_id)` — records **provenance**:
  which document a given field value was extracted from, so queries like "what was the
  committed date for Project X?" can be answered *with a citation*. (May be folded into
  `entities.fields_json` if provenance can be represented there instead; the requirement
  is that each field value can name its source doc.)
- `entity_embeddings(entity_id, embedding)` — vector column for semantic search (deferred
  with the embeddings decision)
- `mentions(doc_id, entity_id, quote, created_at)` — links between docs and entities. The
  **supporting quote** the LLM cited is persisted: it powers the review TUI, explains
  *why* an entity was linked, and surfaces as evidence in query results. Char offsets and
  confidence scores are intentionally omitted at MVP — no target query needs them.
- `ingest_changes(id, doc_id, kind, payload_json, status)` — proposed/approved/rejected changes for resumable ingest

Every markdown write goes through the DB (repository) layer, which updates SQLite in the same transaction.

### Modeling document kind

Documents are **plain text with no type or fields of their own**. Anything that looks like
a document category is instead modeled as an **entity**: a meeting is a `Meeting` entity,
and its transcript/notes is a doc linked to that entity via a mention. The LLM infers a
doc's nature from its content at ingest time. This keeps documents schema-free while still
supporting queries like "all meeting notes related to Project X" — resolved as *docs that
mention both a `Meeting` entity and the `Project X` entity*.

## Ingest Pipeline

`forte doc ingest <path>` executes as a multi-step pipeline. Each step produces "proposed changes" that get persisted to `ingest_changes` and then presented in the TUI (or auto-approved with `--yes`).

Each of steps 2–5 is a **separate LLM call** (not one combined structured-output call).
Separate calls map cleanly to the atomic proposed-change types, are independently
retryable, and keep partial approval / resume simple to reason about. The cost is more
round-trips per ingest. (A future orchestration layer — likely LangGraph — would own this
flow.)

1. **Copy** — source file is copied into `docs/raw/` and registered in `documents`. Original on the user's disk is left untouched.
2. **Extract entities** — LLM reads the doc text and proposes candidate entities (name, schema, supporting quote).
3. **Link to existing** — for each candidate, rule-based matching (exact + alias + normalized name) finds candidate existing entities; the LLM picks the correct match or "none".
4. **Create new** — candidates not linked to an existing entity are proposed as new entities.
5. **Extract structured fields** — for each linked or newly created entity, LLM extracts schema field values from the doc.

Each proposed change is atomic (one new entity, one link, one field-set) and independently approved/rejected in the TUI. Approved changes are written to markdown + SQLite immediately; rejected changes are recorded so they aren't re-proposed on rerun.

### Failure handling

LLM calls can fail on transport errors, rate limits, or malformed/unparseable structured
output. Each call uses **bounded retries, then fails** — the same policy for malformed
output as for transport errors (no separate re-prompting path at MVP). Because proposed
changes are persisted to `ingest_changes` as they are produced, a failed ingest can be
rerun and will **resume from the pending state** rather than starting over.

## Entity Linking

Candidate discovery (deterministic):

- Exact name match
- Exact alias match
- Case/whitespace-normalized name/alias match
- (Future) vector similarity over name + aliases

Candidates plus the surrounding doc context are handed to the LLM, which returns either an existing entity ID or "no match". Only rule-matched candidates are shown — the LLM never invents an entity ID.

## Human Review TUI

- Presents one proposed change at a time with enough context to decide (the source doc excerpt, the affected entity, the change payload).
- Two actions: **approve** or **reject**.
- No inline editing at MVP — corrections happen after ingest via `forte entity edit`.
- `--yes` bypasses the TUI entirely and approves every proposed change.

## Testing

- **Integration-first.** As much of the application as possible is exercised through
  integration tests that drive the real CLI against a temporary vault (real markdown files
  + real SQLite), asserting on end-to-end behavior across the layers.
- **The LLM sits behind a stubbable boundary.** The agentic steps depend on an LLM-client
  abstraction that can be swapped for a stub returning canned responses, making ingest
  tests deterministic and free to run. Live "eval"-style tests against the real model, if
  any, are kept separate from the main suite.

## Configuration

`.forte/config.yaml`:

```yaml
model:
  extraction: claude-haiku-4-5
api_keys:
  anthropic: ${ANTHROPIC_API_KEY}   # env-var interpolation
```

Additional keys added as needed. API keys can be interpolated from environment variables so config files are safe to check into git.

## Resolved Since V0

- **CLI framework** → Click.
- **TUI library** → Rich prompts.
- **Packaging / distribution** → `uv`.
- **Processed markdown format** → verbatim source text + frontmatter; mentions listed in
  frontmatter, no inline markup.
- **Ingest steps 2–5** → separate LLM calls, one per step.
- **Entity/doc IDs** → auto-increment integers.
- **Schema validation** → structural (exact field set), free-text values, cascading
  schema mutations.
- **Ingest identity** → (source path + content hash); updated-source handling punted to a
  warn/block for MVP.
- **LLM failure policy** → bounded retries then fail; resume on rerun.
- **Architecture** → four layers (driver → service → db → domain).
- **Testing** → integration-first with a stubbable LLM boundary.

## Open Questions

- **Embedding provider / vector column** — resolved: provider is local
  `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim); vector storage is a plain BLOB
  column of float32 bytes on `chunks` with brute-force cosine similarity in Python at MVP
  scale, `sqlite-vec` deferred as a future swap-in if the corpus grows enough to need it.
- **Field-value provenance representation** — a dedicated `entity_field_values` table vs.
  encoding source-doc refs inside `entities.fields_json`.
- Per-step model overrides in config (single model vs. one per pipeline step).

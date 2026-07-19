# Product Requirements Document - V0

## Project Overview

Forte is a personal knowledge-base tool that offloads the organizational work of maintaining a second brain to an AI agent (Claude) while keeping the resulting knowledge base fully human-readable. Users drop raw documents into a vault; Forte extracts entities, links them into a knowledge graph, and stores everything as browsable markdown alongside a SQLite index.

MVP is a local Python CLI targeting individual knowledge workers. See [docs/project-overview.md](./project-overview.md) for full domain and product context.

## User Journeys

### UJ1 — First-time setup

1. Ben installs Forte, `cd`s into a new folder, and runs `forte init` to create a vault.
2. He defines two schemas via `forte schema add person` and `forte schema add project`, specifying the fields he cares about.
3. He runs `forte doc ingest ./notes/kickoff.md`.
4. The TUI walks him through each proposed entity, link, and field-set one at a time.
5. He approves the changes that look right and rejects the noise.
6. The processed doc and new entities land under `docs/processed/` and `entities/`, browsable as plain markdown.

### UJ2 — Manual guided ingest

1. Ben has a folder of 20 meeting notes he wants in the knowledge base.
2. For each file, he runs `forte doc ingest <file>` and walks through the review TUI.
3. He approves links to existing people/projects and creates new entities where appropriate. Alias matching correctly proposes "Ben S. → existing `person/ben-sivongxay`" and he approves.
4. When the LLM fails to link correctly and proposes a duplicate new entity, he rejects it.
5. He adds the missing alias to the existing entity via `forte entity edit` and re-ingests the doc — previously approved changes are preserved.

### UJ3 — Exploration

1. Ben wants to find everything related to a project he half-remembers.
2. He runs `forte entity search "onboarding revamp"` and gets a semantic-ranked list.
3. He runs `forte entity show project/onboarding-revamp` to see the entity's fields and the docs it was extracted from.
4. He opens the linked markdown files directly, or via `forte doc show <id>`, to read the source context.

## Functional Requirements

### Init, config, and vaults

- Forte shall provide `forte init` to create a new vault, laying down `.forte/`, `docs/raw/`, `docs/processed/`, and `entities/`.
- Forte shall discover the current vault by walking up from the current working directory to find a `.forte/` directory (git-style).
- Forte shall read model choice, API keys, and basic operational settings from `.forte/config.yaml`.

### Schemas

- As a user, I should be able to define, list, and remove schemas via `forte schema add`, `forte schema list`, and `forte schema remove`.
- Schemas shall support fields of the following types: string, number, date, boolean, list-of-strings, and entity-ref.
- All schema fields shall be optional.

### Entities

- As a user, I should be able to manually create an entity via `forte entity add <schema>`, so that I can pre-register things like "Project X" before the agent has seen any docs mentioning them.
- As a user, I should be able to list, show, edit, and remove entities via `forte entity list`, `forte entity show <id>`, `forte entity edit <id>`, and `forte entity remove <id>`.
- Entity edits shall include the ability to modify aliases, so that users can correct or extend the linking behavior for future ingests.

### Document ingest

- As a user, I should be able to run `forte doc ingest <path>` on a text-based document (md, txt, or text-extractable docx/pdf).
- When the user runs `forte doc ingest <path>`, forte shall:
  - copy the source document into the vault's internal `docs/raw/` folder and register it in the SQLite index, so that the vault does not depend on the user retaining their original copy.
  - 
- Given an ingest run, when Forte proposes a change (a new entity, a link to an existing entity, or a field-set on an entity), then the user shall be prompted to approve or reject that individual change in an interactive TUI.
- Forte shall support a `--yes` flag on `doc ingest` that auto-approves all proposed changes, so that agents can run ingest non-interactively.
- Given an ingest run is interrupted or fails partway through, when the user re-runs ingest on the same document, then previously approved changes shall be preserved and any remaining work shall be re-proposed.

### Entity linking and aliases

- Forte shall use rule-based matching over entity names and aliases to identify candidate existing entities during ingest.
- Forte shall use the LLM to propose the correct link (or "no match, create new") among the rule-matched candidates.
- Entities shall support an `aliases` field as a first-class attribute.

### Query and retrieval

- As a user, I should be able to run `forte doc list` and `forte doc show <id>` to browse ingested documents.
- As a user, I should be able to run `forte entity list [--type X]` and `forte entity show <id>` to browse entities.
- As a user, I should be able to run `forte entity search <query>` and get semantic-search results ranked over entity names, aliases, and content.

## Non-Functional Requirements

- Forte shall be distributed as a Python CLI runnable on macOS and Linux.
- Forte shall support vaults of up to approximately 1,000 documents and a few hundred entities at MVP scale.
- Ingest of a single document shall complete within 30 seconds to 2 minutes on the default extraction model.
- Basic (non-semantic, non-graph) queries such as `entity show`, `entity list`, `doc show`, and `doc list` shall return within 1–2 seconds at MVP scale.
- Forte shall use Claude Haiku as the default extraction model, with per-doc ingest cost targeted at "reasonable" (no hard quantified budget for MVP).
- Forte shall assume single-user, single-process access to a vault at MVP; concurrent writes are not supported.
- The knowledge base is authoritatively stored across both the markdown files and the SQLite index. Corruption of either is treated as system failure and is not automatically recoverable in MVP.
- The knowledge base shall remain fully human-readable: docs and entities are plain markdown files the user can browse, edit, or take elsewhere.

## Out-of-Scope Requirements

The following are explicitly out of scope for MVP:

- Web UI or GUI of any kind
- Multi-user vaults, teams, or permissions
- Cloud sync, hosted storage, or SaaS deployment
- Authentication and account management
- Natural-language query (`forte query`) — planned as an early follow-up
- OCR, audio transcription, web scraping, and email parsing (any format requiring a preprocessing step)
- Schema migration of existing entities when a schema changes
- Bulk `forte reindex` or SQLite rebuild command
- Inline editing of proposed changes during the TUI review (only approve/reject)
- Graph traversal CLI commands (e.g., "entities linked to X", "docs mentioning Y") — the architecture must support these, but they are not exposed in MVP
- Dedicated agent/daemon orchestration layer — MVP relies on manual orchestration via the CLI (user or Claude Code)
- Vector search over entity names/aliases as a linking aid — noted as a future enhancement

## References

- [docs/project-overview.md](./project-overview.md) — Domain, problem statement, product pitch
- [docs/input/interview-project-overview.md](./input/interview-project-overview.md) — Initial scoping interview
- [docs/input/interview-prd.md](./input/interview-prd.md) — PRD inputs interview (source for the requirements in this document)
- [docs/solution-design.md](./solution-design.md) — Implementation details: CLI spec, vault layout, ingest pipeline, storage
- *Building a Second Brain*, Tiago Forte — conceptual inspiration for the project

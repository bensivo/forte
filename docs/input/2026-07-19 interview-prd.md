# Interview - PRD Inputs

- **Topic:** Forte PRD inputs — functional/non-functional requirements, scope, user journeys
- **Interviewee:** Ben Sivongxay (bensivo@gmail.com)
- **Date:** 2026-07-18

## Summary

This interview finalizes the requirements inputs for Forte's MVP PRD, building on the project overview and initial scoping interview. It covers ingest scope, human review shape, entity linking, schema semantics, query capabilities, non-functional targets, failure/data-safety behavior, config, and out-of-scope items. Three illustrative user journeys were selected: first-time setup, manual guided ingest, and exploration.

### Key decisions

- **Ingest scope (MVP):** text-based docs only (md, txt, and text-extractable docx/pdf). Anything requiring preprocessing (OCR, audio, web scraping, email) is deferred.
- **Human review:** atomic approve/reject per proposed change (new entity, link to existing entity, field-set). No inline editing in MVP. `--yes` auto-approve is must-have.
- **Entity linking:** rule-based candidate discovery (incl. alias matching), LLM proposes the link. Aliases are first-class on entities. Vector search over names/aliases is a nice-to-have.
- **Schemas:** MVP field types — string, number, date, boolean, list-of-strings, entity-ref. All fields optional. Schema migrations out-of-scope for MVP; future work covers reprocessing docs when non-trivial schema changes happen.
- **Query:** `entity search` is semantic. Graph traversal deferred from MVP CLI surface, but architecture must support it (foundation for future agent orchestration).
- **Scale/perf (MVP):** up to ~1k docs / few hundred entities. Ingest 30s–2min/doc acceptable. Basic (non-semantic, non-graph) queries <1–2s. Single-user, single-process.
- **Failure/data safety:** partial ingest progress is preserved (docs can be reprocessed). Raw source docs are **never** modified or deleted — extractions produce new docs linked back to the original. SQLite is authoritative alongside markdown (not treated as derived/rebuildable); no bulk `forte reindex` command.
- **Config:** model choice, API keys, basic operational settings in `.forte/config.yaml`.
- **Vaults:** CWD-based discovery (git-style) — supports one vault per project.
- **Out of scope for MVP:** web UI, multi-user, cloud/sync, auth, natural-language query (last of these is "soon in scope").

### Draft functional requirements

**Init & config**
- Forte shall discover the current vault by walking up from CWD to find a `.forte/` directory (git-style).
- Forte shall provide `forte init` to create a new vault (`.forte/`, `docs/`, `entities/`).
- Forte shall read model choice, API keys, and operational config from `.forte/config.yaml`.

**Schemas**
- As a user, I should be able to define, list, and remove schemas via `forte schema add/list/remove`.
- Schemas shall support fields of type: string, number, date, boolean, list-of-strings, entity-ref.
- All schema fields shall be optional.
- Schema migration of existing entities is out-of-scope for MVP.

**Document ingest**
- As a user, I should be able to run `forte doc ingest <path>` on a text-based document (md, txt, docx, pdf).
- Forte shall never modify or delete raw source documents.
- Forte shall produce a processed doc linked to the original for each ingest.
- Given an ingest run, when Forte proposes a change (new entity, link to existing entity, or field-set on an entity), then the user shall be prompted to approve or reject that individual change in a TUI.
- Forte shall support a `--yes` flag that auto-approves all proposed changes for non-interactive/agent use.
- Given an ingest run is interrupted or fails partway, when the user re-runs ingest on the same doc, then previously approved changes shall be preserved and remaining work re-proposed.

**Entity linking**
- Forte shall use rule-based matching (name + aliases) to identify candidate existing entities during ingest.
- Forte shall use the LLM to propose the correct link (or "no match, create new") among candidates.
- Entities shall support an `aliases` field as first-class.

**Query & retrieval**
- As a user, I should be able to run `forte doc list` / `doc show <id>` and `forte entity list [--type X]` / `entity show <id>`.
- As a user, I should be able to run `forte entity search <query>` and get semantic-search results over entity names and content.
- Basic (non-semantic, non-graph) queries shall return within 1–2 seconds for MVP scale.

### Draft non-functional requirements

- Forte shall support vaults of up to ~1,000 documents and a few hundred entities at MVP.
- Ingest of a single document shall complete within 30 seconds to 2 minutes on the default model (Claude Haiku).
- Forte shall use Claude Haiku as the default extraction model, with cost as a "reasonable" (non-quantified) target.
- Forte shall assume single-user, single-process access to a vault at MVP.
- Forte shall be distributed as a Python CLI runnable on macOS and Linux.

### Explicitly out of scope for MVP

- Web UI or GUI of any kind
- Multi-user, teams, permissions
- Cloud sync, hosted storage
- Authentication / accounts
- Natural-language query (`forte query`) — planned as an early follow-up
- OCR, audio transcription, web scraping, email parsing
- Schema migration of existing entities
- Bulk `forte reindex` / SQLite rebuild
- Inline editing of proposed changes during TUI review
- Graph traversal commands (`entity related`, `doc mentions`, etc.) — architecture must support these for future

### User journeys

**UJ1 — First-time setup**
Ben installs Forte, `cd`s into a new folder, runs `forte init`. He defines two schemas via `forte schema add person` and `forte schema add project` (specifying fields). He runs `forte doc ingest ./notes/kickoff.md`; the TUI walks him through each proposed entity and field-set. He approves the ones he wants and rejects the noise. The processed doc and new entities land under `docs/processed/` and `entities/`.

**UJ2 — Manual guided ingest**
Ben has a folder of 20 meeting notes he wants in the knowledge base. For each file, he runs `forte doc ingest <file>` and walks through the review TUI, approving links to existing people/projects and creating new entities where appropriate. When entity linking correctly proposes "Ben S. → existing person/ben-sivongxay" via alias matching, he approves. If the LLM fails to link correctly, he rejects the "new entity" proposal and re-ingests after adding an alias.

**UJ3 — Exploration**
Later, Ben wants to find everything related to a project he half-remembers. He runs `forte entity search "onboarding revamp"` and gets a semantic-ranked list. He runs `forte entity show project/onboarding-revamp` to see the entity's fields and the docs it was extracted from. He opens the linked markdown files directly (or via `forte doc show`) to read the source context.

## Interview Log

**Q:** Let's start with ingestion scope for MVP. The overview lists markdown, docx, PDF, and transcripts as target formats. For the MVP release specifically, which of these are **must-haves** vs. **nice-to-haves**? And are there any formats you want to explicitly defer (e.g., images with OCR, audio files, web URLs, email exports)?
**A:** MVP, we can just do text-based docs. We can leave out anything that requires a pre-processing step as a future feature.

**Q:** On the **human-in-the-loop TUI review** step during ingest. What's the minimum viable review experience? Specifically:
- What should the user be able to do at the review step? (e.g., approve/reject each extracted entity, edit entity fields inline, merge with existing entity, rename, skip)
- Is it one review per document, or one big review at the end of a batch?
- And is the `--yes` auto-approve flag a must-have for MVP, or can it wait?

**A:** Lets do 1 review per extracted item (for each entity, for each link to an existing entity, for each instance of 'set these fields on this entity',) They can either approve or reject the proposed change.

The --yes is a must-have.

**Q:** On **entity linking / deduplication**. When ingesting a new doc, how should Forte decide that "Ben S." in the new doc is the same as an existing `person/ben-sivongxay.md` entity?
- Should it be LLM-driven (Claude sees candidates and proposes links)?
- Rule-based (name/alias matching)?
- Both?
- And should entities support **aliases** as a first-class field so "Ben", "Ben S.", "bensivo" all resolve to one entity?

**A:** We can used rules for finding candidates, and llm for proposing the links. We should definitely support aliases.

As an aside, it might be useful to add some kind of vector search on entity names and aliases to make this easier

**Q:** On **schemas** (user-defined entity kinds). A few sub-questions bundled since they're tightly related:
- What field **types** need to be supported in MVP? (e.g., string, number, date, boolean, list-of-strings, reference-to-another-entity)
- Are fields **required vs. optional**, and does the LLM get told which is which during extraction?
- What happens when a user **modifies a schema** after entities already exist under it (add field, remove field, rename)? Migrate, ignore, or out-of-scope for MVP?

**A:** The field types you listed are good for an MVP.

All fields will be optional.

We'll ignore schema migrations for MVP - but in the future, we'll need some kind of re-processing of old docs with new schemas once schemas change (unless it's just deleting or renaming a field)

**Q:** On **querying and retrieval** in MVP. The command surface lists `entity list`, `entity show`, `entity search`, `doc list`, `doc show`. Two questions:
- What should `entity search <query>` actually do? Substring match on name/aliases? Full-text over entity fields? Semantic/vector? Or just the simplest thing that works?
- Should users be able to traverse the graph from the CLI — e.g., "show me all docs that mention entity X" or "show me all entities linked to entity Y"? Or is that deferred?

**A:** Ideally, `entity search` is a semantic search.

Traversing the graph via the CLI is maybe not required in this first iteration, but it's definitely going to be a core feature of the agentic orchestration features we build on top of th eknowledge base. So we should plan for it

**Q:** On **non-functional requirements**. Let's cover the boring-but-critical stuff:
- **Scale targets for MVP**: rough upper bound on vault size? (e.g., "hundreds of docs, thousands of entities" vs "tens of thousands")
- **Performance expectations**: any latency targets for ingest (per doc) or query (`entity search`, `entity show`)?
- **Cost sensitivity**: any rough per-doc-ingest budget you're targeting with Haiku, or is "reasonable" fine?
- **Concurrency**: single-user, single-process assumption fine for MVP, or do we need to worry about two agents ingesting simultaneously?

**A:** I'm thinking hundreds of docs with dozens of entities for MVP scope. Maybe getting up to a thousand docs and a couple hundred entities at the most for now.

Ingest is fine if takes 30 seconds to 1-2 minutes, but basic (not semantic or graph) query should be faster, like within 1-2 seconds.

**Q:** On **failure modes and data safety**. A few bundled:
- If ingest fails partway through (LLM error, crash, user Ctrl-C mid-review), what should happen? Roll back all changes, keep partial progress, or leave the doc in a "quarantine" state?
- Should Forte ever **modify or delete** raw source docs the user drops in, or is `docs/raw/` strictly read-only after ingest?
- Do you want a **`forte reindex`** that fully rebuilds SQLite from the markdown files as the authoritative recovery path? (Overview implies yes — just confirming it's must-have for MVP.)

**A:** Keep the partial progress, we shoudl add an ablity to re-process docs anyways.
Forte should NEVER modify or delte the raw docs. Any extraction should create a new doc, linked to the original.
We don't need a full 'forte reindex' over the entire knowledge base as a sinlge command. If we never modify originals, a user could reasonably just write a script to reindex docs themselves.

**Q:** Quick clarification: the SQLite index is described as "derived, rebuildable." If it gets corrupted or out-of-sync, what's the recovery path? A per-doc reprocess loop the user scripts themselves, or should there be a lower-level `forte index rebuild` primitive (distinct from re-running LLM extraction)?

On **user journeys** — I'd like to draft 3–4 illustrative journeys for the PRD. Which of these resonate as the most important to showcase? Pick any that fit or suggest others:
- **A.** First-time setup: `forte init`, define first schemas (person, project), ingest first doc, review extractions.
- **B.** Bulk backfill: user points Forte at a folder of 50 existing notes, runs ingest with `--yes`, later reviews and cleans up entities.
- **C.** Agent-driven ingest: Claude Code drives `forte doc ingest --yes` on new docs as they arrive, user reviews entities weekly.
- **D.** Exploration: user searches for an entity, opens it, sees linked docs, reads them.
- **E.** Schema evolution: user adds a new field to `Project`, updates a few existing project entities manually.

**A:** I'm actually okay if the SQLIte index is not considered 'derived, rebuildable' lets remove that as a requirement. It is okay if the knowledge-base depends on both the MD files and the Sqlite db, and corruption of either breask the system.

Do UJs for first time setup, manual guided ingest, and exploration

**Q:** A few smaller clarifications bundled to wrap up:
- **Config**: anything user-configurable in `.forte/config.yaml` for MVP beyond model choice (e.g., Anthropic API key location, default schemas, ingest prompts)?
- **Multi-vault**: does the CLI need to support multiple vaults (e.g., `--vault` flag or cwd-based discovery like git), or is one-vault-per-invocation-cwd fine?
- **Explicit out-of-scope for MVP**: anything you want called out that people might otherwise assume is in (e.g., no web UI, no multi-user, no sync/cloud, no auth, no natural-language query, no auto-ingest/watch mode)?

**A:** Model choice, api keys, basic operational configs are good. If we think of anything else we can add it later.
Lets do vaults based on CWD, I can see people wanting to have a vault per project.

Out of scope: web ui, multi-user, cloud, auth, natural-language query (but very soon in scope)

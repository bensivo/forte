# Interview - Solution Design

- **Topic:** Solution design / implementation approach for Forte MVP
- **Interviewee:** Ben Sivongxay (bensivo@gmail.com)
- **Date:** 2026-07-18
- **Related docs:** [solution-design.md](../solution-design.md), [prd.md](../prd.md)

## Summary

This interview resolved the open questions in the V0 solution design and filled in
several gaps around schemas, IDs, ingest identity, failure handling, architecture, and
testing. Key takeaways:

- **Stack decisions locked:** `uv` for packaging/distribution, **Click** for the CLI,
  **Rich prompts** for the interactive approve/reject TUI.
- **Embeddings deferred:** the semantic `entity search` and embedding-provider choice
  (local `sentence-transformers` vs. hosted like Voyage) are punted pending spikes on
  performance, ease of use, and cost.
- **Ingest LLM calls stay separate** per pipeline step (not one mega structured-output
  call), with **LangGraph** anticipated as the future orchestration layer.
- **Schemas are structurally validated:** every entity of a schema must carry exactly
  that schema's field set (empty values allowed, no missing/extra fields). Fields are
  free-text (no value validation). Fields defined via repeated `--field` flags;
  `forte schema add-field` anticipated. Schema mutations **cascade automatically** —
  adding a field back-fills existing entities with empty values, removing strips it.
- **Every entity has built-in `name` (required) + `aliases`,** separate from schema fields.
- **IDs are auto-increment integers** for entities and docs.
- **Processed docs** = verbatim original text + YAML frontmatter (back-link to `raw/` +
  flat list of mentioned entity IDs). No inline markup.
- **Ingest identity = (source path + content hash).** Same path + new hash = updated
  source. For MVP this is **detected and warned/blocked**; **full replace** with entity
  reconciliation is the future behavior.
- **LLM failures use bounded retries then fail** (transport errors and malformed output
  alike); persisted proposals let a rerun resume.
- **Four-layer architecture:** driver/controller (Click + Rich) → service (pipeline) →
  db (markdown + SQLite dual-write) → domain (models + invariants).
- **Integration-first testing** with the LLM behind a stubbable boundary.
- **`mentions` record `(doc_id, entity_id, quote, created_at)`;** field values carry
  source-doc provenance. No offsets/confidence at MVP.
- **Doc "kind" is modeled as an entity, not a doc attribute** — a `Meeting` entity with
  its notes linked as a doc — so docs stay plain text with no doc-schema machinery.
- **Solo developer, ~a few weekends, AI-agent-assisted** implementation once the spec is
  locked. Tight, well-specified scope prioritized.

## Interview Log

Q: You mentioned some things are already decided. The doc lists several "TBD" items — CLI
framework (Click vs Typer), TUI library (Textual vs Rich), and embeddings provider. Which
of these (or any other stack choices) have you actually locked in since this doc was
written, and what's still genuinely open?

A: Very few. I know we want to use UV as a package manager. I have used click before, so
lets go with that. I haven't used any TUI libraries, so just go with what's most popular,
as long as it's easy to build with. For embeddings, open to suggestions.

Q: [Recommendation given] For TUI, I'd go with **Rich prompts** over Textual for a strict
one-change-at-a-time approve/reject flow — most widely used, and the interaction is
inherently sequential, so you don't need Textual's app/event loop. For embeddings,
Anthropic doesn't ship a first-party embeddings API (they recommend Voyage AI); realistic
options are local `sentence-transformers` (no extra key, offline, but heavy `torch` dep)
or a hosted embedding API (light dep, another key + network). Given this is a local-first
vault tool, I lean local sentence-transformers. Does that TUI + embeddings direction sound
right, or keep embeddings hosted?

A: Great, lets use Rich prompts. Lets actually leave the embeddings decision off for now.
I think it'll take some spikes to investigate both and understand performance, ease of
use, etc.

Q: One of your open questions is whether ingest steps 2–5 (extract entities → link →
create → extract fields) are separate LLM calls or one big structured-output call. My
instinct: keep them as separate calls — each maps cleanly to an atomic proposed-change
type, they're independently retryable, and a single mega-call makes partial approval and
resume much harder. The tradeoff is more latency and token cost per ingest. Do you want
separate calls per step, or are you optimizing for fewer round-trips?

A: Separate calls. I'm thinking we'll actually use something like langgraph for this in
the future.

Q: Let's talk schemas. `forte schema add <name>` defines an entity kind and its fields. Do
fields have types (string / number / date / list / enum), or is everything free-text
strings at MVP? And is field validation enforced on write, or is the schema purely a hint
to the LLM for extraction?

A: Schemas definitely have fields, but free-text is fine for now. No field validation,
because all fields are optional.

Q: How should `forte schema add <name>` take the field list? (a) interactive Rich prompts
asking for field names one at a time, (b) command-line flags like `--field role --field
company`, or (c) create an empty schema and add fields later via editing?

A: Actually change that, the fields should be validated, at least the schema of fields
themselves. Every entity of a schema should definitely have all the fields listed, just
with empty values allowed. And no fields should show up that were not in the schema. Use
`--field role --field company` for now. But I suspect we'll want more specific commands
like `forte schema add-field` as well.

Q: When a schema changes — say you add a field to a schema that already has 20 entities —
what happens to the existing entities? Do they get back-filled with an empty value
automatically (to preserve the invariant), or is that a migration the user runs
explicitly? Same for removing a field.

A: Backfill with an empty value.

Q: The CLI uses `<id>` throughout. What is an id, concretely? (a) an opaque UUID, (b) an
auto-increment integer from SQLite, or (c) the slug derived from the entity name? Slugs
are most human-typeable but break on rename and can collide. What do you want IDs to be —
and if opaque, how does a user find the id to type it?

A: Lets go with auto-increment integers for now. We could also force all entities to have
a required 'name' field.

Q: Let's nail the processed-doc format. After ingest, `docs/processed/` holds the
post-extraction markdown. (1) What's in it — basically the extracted plain text of the
source with frontmatter linking back to `raw/` and listing extracted entity IDs? And (2)
how are mentions represented — just a list in frontmatter, or inline in the body (e.g.
`[[entity]]`-style links)? Inline links are richer but much harder to place reliably from
an LLM.

A: The processed docs are the text of the original doc + yaml frontmatter + links, which
are fine to just list in the frontmatter.

Q: The doc says rerunning `forte doc ingest <same path>` skips the copy step because the
doc is "already present." How is "same document" detected? By source file path, by a
content hash of the file, or by the resulting filename in `raw/`? Path is simplest but
breaks if the file moved or two files share a name; a content hash is robust to
renames/moves but treats an edited version as brand new. Which do you want?

A: Lets do source filepath + content hash. I know it adds more complexity, but I can see
people updating the source file, then wanting to push the update to the knowledgebase. In
that case we'll need to know that the old doc has been replaced, and to handle that
accordingly.

Q: Let's define that update case. When someone re-ingests an updated source doc (same
path, new hash), what should happen at MVP? (a) Full replace: retire the old copies and
re-run extraction from scratch, reconciling entities; (b) Version alongside: keep the old
copy, add the new one as a separate version; (c) Punt for MVP: detect it, warn "this
source changed since last ingest," and require an explicit `--update` flag.

A: Lets punt for MVP, but full replace is what we'll do in the future.

Q: Failure handling in the ingest pipeline. Each step makes an LLM call that can fail —
network error, rate limit, or malformed/unparseable structured output. What's the desired
behavior when a step fails mid-ingest? (a) fail the whole ingest and leave persisted
proposals for a rerun to resume; (b) retry the failing call some number of times before
giving up; (c) both. And for malformed LLM output specifically, automatic re-prompting or
just a failed step?

A: B.

Q: The doc mentions a "repository layer" but doesn't lay out the package structure. Do you
have a preferred internal layering? I'm picturing CLI/command layer (Click) → service/
pipeline layer → repository layer (markdown+SQLite dual-write) → model/LLM clients. Does
that match, and any particular structure/convention you want the team to follow?

A: I'm a fan of a domain layer, service layer, a db layer, and a driver / controller
layer.

Q: Testing strategy — especially around the LLM, which is nondeterministic and costs money
to call. How do you want the team to test the ingest pipeline? Mock/stub the LLM at the
service boundary; record-and-replay real responses (fixtures/cassettes); or a small set of
live "eval" tests run separately? And is there a coverage bar, or is pragmatic unit
coverage of domain/db enough?

A: Lets have as much of the application testable with good integration testing frameworks.
For the testing of the agentic part, lets have some mechanism for stubbing the LLM
responses.

Q: The SQLite schema has `mentions(doc_id, entity_id, ...)` with the fields left open.
Beyond the link itself, what should a mention record? The supporting quote/excerpt, a
char offset/location, a confidence score, or just the bare pair for MVP?

A: What do you think would be useful to be able to query when searching the knowledge
base? The questions we'll be asking are things like: "Get me all the meeting notes related
to Project X", "What was the committed date for Project X?", "List me all the people who've
attended meetings about Project X (and what meetings they were in)".

Q: [Reasoning back from those queries] "All meeting notes related to Project X" is a
doc↔entity join filtered by document kind — which docs don't currently have. "List all
people who attended meetings about Project X" is graph traversal (Project X → docs →
Person entities). "Committed date for Project X" is reading a field value on the entity,
where the interesting part is provenance (citing the source doc). Recommendation:
`mentions` = `(doc_id, entity_id, quote, created_at)` — keep the supporting quote (powers
the review TUI, explains why, shows evidence); skip offsets/confidence for MVP. Also
capture which doc a field value came from (field provenance). Bigger question: your queries
all filter on document kind, but docs have no type. Do you want documents typed/
categorized, and should docs carry extractable fields of their own, or is all structured
data pushed onto entities?

A: For now, lets leave that all in the entities, and leave the docs as just text. For
example, we could create a "Meeting" entity, then link the transcript / notes of that
meeting as a doc. An LLM should be able to see that that doc is a meeting note once it sees
it.

Q: Almost done. Logistics: (1) What's the timeline / team size for this MVP? (2) The doc
says `pipx`-installable, but you've chosen `uv` — do you want distribution to be `uv tool
install` / `uv`-based as well, or keep `pipx` as the user-facing install path while using
`uv` for dev?

A: It's just me working on it, I want this core functionality done in a few weekends,
using AI agents to do lots of the coding, once we're done with the spec. We can make
everything UV for now. And adjust distribution later.

Q: Anything I haven't asked about that you want captured before I write this up? For
example: config (per-step model overrides, embedding settings), how `entity edit`
interacts with the dual-write, logging/observability for debugging agent behavior?

A: I'm good. Lets serialize this into an interview doc, and also update the solution-design
doc with all the details.

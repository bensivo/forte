# Agent Layer — Tasks

Feature: Embed the AI agent layer natively into the `forte` binary, so a user with just the CLI + an Anthropic API key gets entity extraction, linking, and field extraction with **zero external-agent harness** (the hand-driven `ingest` Claude Code skill is thrown away). Driven by [docs/input/2026-07-20 interview-agent-layer.md](../../input/2026-07-20%20interview-agent-layer.md), [prd.md](../../prd.md) ("Document ingest", "Entity linking and aliases", UJ1/UJ2), and [solution-design.md](../../solution-design.md) ("Ingest Pipeline", "Entity Linking", "Human Review TUI", "Testing").

**Command surface delivered by this feature:**
- `forte doc ingest <path>` — unchanged, deterministic (copy + text-extract + register). Already built.
- `forte agent process <doc-id> [--yes] [--dry-run]` — the LLM workhorse: extract → review → link/create → review → field-extract → review → commit.
- `forte agent ingest <path> [--yes] [--dry-run]` — convenience wrapper = `doc ingest` then `agent process`.

**Key architectural decisions locked in the interview (read before starting any task):**
- **Split by cost/determinism, not by noun.** Anything deterministic and free (doc preprocessing, rule-based candidate matching) lives in core `forte`. Anything that burns tokens lives under the `forte agent` namespace.
- **Embedded structured pipeline (design-doc option A), not a tool-using agent loop.** Forte owns control flow; the LLM fills structured blanks via discrete, separate SDK calls (one per step). A tool-loop is a *future* effort (the "chat with your KB" feature) — so the pipeline's internal operations should be a clean, reusable capability layer a future loop can wrap as tools.
- **Stepwise review with all state in-memory (design-doc option B).** extract → review → link/create → review → field-extract → review. **No `ingest_changes` persistence, no resume.** Ctrl-C loses in-flight progress (acceptable). Everything commits at the very end. The `ingest_changes` table exists in the schema but stays **unused** by this feature.
- **Commit is best-effort**, not atomic across markdown + SQLite; report successes and failures. Mechanical `doc ingest` happens up front, so Ctrl-C leaves the doc ingested (harmless — duplicate-ingest is already a no-op).
- **Decoupled from the CLI/Rich presentation layer.** The app is eventually becoming a GUI/web app (upload → loaders → proposed entities → Approve button). The pipeline must be drivable by a web request/response cycle, so **no Click/Rich calls inside the pipeline or steps** — presentation goes through a small reviewer/reporter seam.
- **LLM boundary:** first-class structured/JSON output (verified: the Anthropic Python SDK supports `messages.parse()` / `output_config={"format": {"type": "json_schema", ...}}`). Stub at the **low-level `messages()`** boundary so tests exercise real parse/validate and can inject malformed JSON. **Single model** for all steps (PRD default `claude-haiku-4-5`; Haiku 4.5 supports structured outputs).
- **Retry policy:** each step retries up to **5 times** (transport error *or* unparseable/invalid JSON), then the whole run fails and **nothing commits**.
- **Embeddings deferred** — rule-based linking only (exact + alias + normalized). Perf hit at scale accepted.
- **Prompts live in source code** for now (per-vault override is a noted future feature). **Quote capture is in** (powers the review evidence). Field-value provenance is **deferred** (write field values into `entities.fields_json` via the existing entity service; do not populate `entity_field_values`).
- **Cost/usage reporting is in** — report token usage + estimated cost per run.

---

- Write `forte agent` behavior spec
- Add config loading (model + API key from `.forte/config.yaml`)
- Build the LLM client abstraction with a stubbable `messages()` boundary
- Build the structured-call helper (bounded 5-retry + JSON parse/validate + usage capture)
- Define pipeline domain models (proposed changes, in-memory run state, usage accumulator)
- Implement rule-based candidate matching (core, non-LLM)
- Author the in-source prompt templates for the three LLM steps
- Implement pipeline step: extract entities
- Implement pipeline step: link candidates to existing entities
- Implement pipeline step: extract structured fields
- Define the reviewer seam + auto-approve/dry-run behaviors (presentation-decoupled)
- Implement the interactive Rich review TUI
- Implement the pipeline orchestrator (stepwise state machine, option B)
- Implement best-effort commit + successes/failures reporting
- Implement cost/usage reporting
- Wire `forte agent process <doc-id>` command and the `agent` group
- Wire `forte agent ingest <path>` convenience wrapper
- Remove the `ingest` skill

---

Task: Write `forte agent` behavior spec
ACs:
- A new spec file `docs/spec/forte-agent.md` exists, following the structure of `docs/spec/forte-doc.md` (title + short intro, `## Scenarios` with Gherkin blocks, `## Out of scope`).
- Scenarios cover, at minimum, observable CLI behavior (stdout, exit code, on-disk files, DB rows) for:
  - `agent process <doc-id>` on an ingested doc, with a **stubbed LLM**: walks the user through proposed entities one at a time, then proposed links, then proposed field-sets; approved changes land as entity markdown files + `entities`/`mentions` rows; rejected changes are not written.
  - `agent process <doc-id> --yes`: auto-approves everything non-interactively; the run prints a summary and exits 0.
  - `agent process <doc-id> --dry-run`: proposes and (optionally, per chosen presentation) reviews, but writes **nothing** to markdown or SQLite; exits 0; a follow-up `doc show`/`entity list` proves no changes landed.
  - `agent process` on a **non-existent doc-id** exits non-zero with a clear error, writes nothing.
  - `agent process` when a step's LLM call fails all retries: the whole run aborts non-zero with a clear error and **nothing is committed** (verify no new entities/mentions).
  - A step returning **zero results** (e.g. no entities extracted) skips cleanly to the next stage / to done, exits 0.
  - Linking: a candidate whose name exactly/alias/normalized-matches an existing entity is proposed as a **link** to that entity (approving it creates a `mentions` row, not a duplicate entity); a candidate with no rule match is proposed as a **new entity**.
  - Quote capture: an approved mention persists the supporting quote the LLM cited (assert the `mentions.quote` column is non-empty).
  - Field extraction only sets **empty** schema fields and never overwrites a non-empty existing field value (matches the conservative behavior the old skill used).
  - `agent ingest <path>`: ingests the file (same as `doc ingest`) then runs `agent process` on it, in one command; `--yes`/`--dry-run` flow through.
  - Cost reporting: a completed run prints a token-usage / estimated-cost summary line.
  - Any `agent` subcommand run **outside a vault** exits non-zero with the shared "Not inside a Forte vault" error and does nothing.
Implementation Notes:
- Specs are the source of truth per CLAUDE.md and drive the integration tests written in the command/pipeline tasks. Write this first.
- Tests must be deterministic and free — every scenario runs against the **stubbed LLM boundary** (see the LLM-client task), never a live model. Note explicitly in the spec that live-model "eval" tests, if any, are kept out of the main suite (matches solution-design "Testing").
- Put explicitly **out of scope**: `ingest_changes` persistence / resumable-resume (state is in-memory only), embeddings / vector candidate discovery / `forte entity search`, per-vault prompt overrides, per-step model overrides, field-value provenance (`entity_field_values`), inline editing of proposed changes in the TUI (approve/reject only), batch/folder processing (one doc at a time).

Task: Add config loading (model + API key from `.forte/config.yaml`)
ACs:
- `src/forte/services/config.py` gains a **reader** (e.g. `load_config(root) -> Config`) that parses `.forte/config.yaml` into a typed object exposing at least: the extraction model id (default `claude-haiku-4-5` when unset) and the Anthropic API key.
- API keys support **environment-variable interpolation** (`anthropic: ${ANTHROPIC_API_KEY}`) per solution-design "Configuration", so a committed config is safe.
- `write_default_config` is updated to lay down the documented structure (model + api_keys with env interpolation) instead of the current bare comment stub; the `forte init` tests are updated to match.
- A typed error (e.g. `MissingAPIKeyError`) is raised when the resolved API key is empty/unset, so the CLI can surface a clear "set ANTHROPIC_API_KEY or configure `.forte/config.yaml`" message. This check is only triggered on the agent path — deterministic commands must not require a key.
- Unit tests cover: default model when unset, explicit model override, env-var interpolation (set/unset), and the missing-key error.
Implementation Notes:
- This is a prerequisite for the LLM client — currently `config.py` is a write-only stub with no reader and no yaml parsing; `pyyaml` is already a dependency (used by entity/doc markdown).
- Keep this in the **service layer**; the LLM client and CLI read config through it. Do not scatter `os.environ` reads across the codebase.
- Config shape to target (from solution-design): `model.extraction`, `api_keys.anthropic` with `${VAR}` interpolation. Additional keys added later as needed — keep the reader tolerant of unknown keys.

Task: Build the LLM client abstraction with a stubbable `messages()` boundary
ACs:
- A new module (e.g. `src/forte/services/llm.py`) defines a narrow `LLMClient` protocol/ABC whose stub boundary is a **low-level `messages()`-style method** — takes the request (model, system, messages, and the structured-output/json-schema config) and returns the raw response (the text/JSON string the model produced **plus** token usage: input, output, and any cache tokens).
- A real implementation wraps the Anthropic Python SDK (`anthropic` added to `pyproject.toml`), constructed with the model + API key from the config reader. It uses **first-class structured output** — `client.messages.parse()` or `output_config={"format": {"type": "json_schema", "schema": ...}}` on `messages.create()` — so the model is constrained to emit schema-shaped JSON. It returns the raw JSON text (not yet parsed into domain objects) and the usage numbers, so the parse/validate/retry layer above sits on real bytes.
- A stub implementation returns caller-supplied canned responses per call, and can be scripted to return **malformed / schema-violating JSON** and to raise transport-style errors, so the retry/validate layer and pipeline tests can exercise every failure branch deterministically.
- Unit tests: the stub returns queued responses in order and surfaces usage; the real client is thin enough that its construction (model/key wiring) is covered but live calls are **not** in the main suite.
Implementation Notes:
- Stub at `messages()`, **not** at a high-level "one method per step" boundary — the interview is explicit: tests must be able to inject invalid JSON (missing fields, typos, wrong enums) and see the parse/validate path react. The per-step convenience lives one layer up (the structured-call helper), which is what the pipeline steps call.
- Model default `claude-haiku-4-5` (PRD); single model for all steps. Do **not** send `temperature`/`top_p`/`top_k` — not needed and rejected on newer models; keep the request minimal (model, system, messages, `max_tokens`, structured-output format). Use adaptive thinking only if a step demonstrably needs it — default to no `thinking` config for these small structured extractions.
- The SDK already auto-retries 429/5xx with backoff; that's fine, but the **5-retry-including-malformed-JSON** policy lives in the structured-call helper above this boundary (malformed JSON is not an HTTP error, so the SDK won't retry it). Keep this client a thin pass-through: one request in, raw text + usage out, transport errors propagated.
- Keep this decoupled from Click/Rich — it's service-layer infrastructure the future web layer will reuse verbatim.

Task: Build the structured-call helper (bounded 5-retry + JSON parse/validate + usage capture)
ACs:
- A helper (e.g. `structured_call(llm, request, schema/model) -> (parsed, usage)`) sits above `LLMClient`: it invokes `messages()`, parses the returned text as JSON, validates it against the expected per-step shape (a dataclass/`TypedDict`/pydantic model — pick one and be consistent), and returns the parsed structure plus the call's token usage.
- On **any** failure — transport error surfaced by the client, JSON that doesn't parse, or JSON that parses but violates the expected shape (missing field, wrong type, invalid enum) — it retries, up to **5 attempts total**. If all 5 fail, it raises a typed error carrying the last failure detail.
- The number of retries is a single named constant (5) so it's trivially tunable later.
- Unit tests (against the stub client) cover: success on first try; success after N transient failures; malformed JSON exhausting all 5 retries then raising; schema-valid-but-wrong-enum treated as a validation failure and retried; usage returned on success.
Implementation Notes:
- This is the reusable "LLM fills a structured blank" primitive every pipeline step calls — keeping it separate keeps the steps tiny and keeps the retry policy in exactly one place. It is also the natural thing a future tool-loop would wrap.
- Per solution-design "Failure handling": same bounded-retry policy for malformed output as for transport errors — there is no separate re-prompting path at MVP.
- Do not commit anything here and do not catch-and-swallow the final failure — the pipeline relies on it propagating so the whole run aborts with nothing written.
- Return usage in a shape the run-level accumulator (usage-reporting task) can sum across all calls.

Task: Define pipeline domain models (proposed changes, in-memory run state, usage accumulator)
ACs:
- A domain/service module defines the vocabulary the whole pipeline speaks, as plain in-memory dataclasses (no DB, no Click):
  - A **candidate entity** (name, schema, supporting_quote) produced by extraction.
  - A **proposed change** union covering the three atomic, independently-approvable kinds: *new entity*, *link to existing entity* (entity id + supporting quote), and *field-set on an entity* (target entity ref + field values, tagged with the source doc). Each carries the supporting quote / doc excerpt needed for review.
  - A **run state** object holding the doc, the current stage, the working set of candidates/proposals, and their approve/reject decisions — **entirely in memory** (no `ingest_changes` rows).
  - A **usage accumulator** that sums token usage (input/output/cache) across every LLM call in the run.
- Unit tests construct each model, exercise the accumulator summing multiple calls, and assert the proposed-change union round-trips the fields the reviewer and committer need.
Implementation Notes:
- These types are the seam between the pipeline and its presentation: the reviewer consumes proposed changes and records decisions on them; the committer consumes approved changes. Keep them free of any Click/Rich/DB imports so the future web layer can serialize them to a request/response.
- **In-memory only** — do not add a repository for these, do not touch the `ingest_changes` table. Ctrl-C dropping everything is intended.
- Mirror the atomic-change granularity from solution-design "Ingest Pipeline": one new entity, one link, one field-set — each independently approved.

Task: Implement rule-based candidate matching (core, non-LLM)
ACs:
- A **deterministic, non-LLM** matcher (core `forte`, e.g. `src/forte/services/linking.py`) takes a candidate name (+ its schema) and the vault's existing entities and returns the set of candidate existing entities via: exact name match, exact alias match, and case/whitespace-normalized name/alias match (per solution-design "Entity Linking").
- Matching is scoped/annotated by schema so a Person candidate isn't matched against a Project of the same string unless that's intended — decide and document the scoping rule.
- Returns an empty set when nothing matches (the signal that the candidate should become a new entity).
- Unit tests cover: exact hit, alias hit, normalized (case/whitespace) hit, no-match, and that the LLM is never invoked (this function takes only data, no LLM client).
Implementation Notes:
- This is explicitly **core, free infrastructure**, not under `forte agent` — the interview calls out rule-based candidate matching as living in core `forte`. Only the *pick-the-right-one-or-none* decision (next task) uses the LLM.
- Reuse the existing `EntityRepository.list()` to enumerate entities; don't query SQLite directly here — keep it a pure function of (candidate, entities) so it's trivially testable and reusable by the future embeddings-based discovery.
- Vector/embedding similarity is **deferred** — leave a clearly-commented seam where a future candidate source would union in.

Task: Author the in-source prompt templates for the three LLM steps
ACs:
- A prompts module (e.g. `src/forte/services/prompts.py`) holds the system/user prompt templates for: (1) extract entities, (2) link a candidate among rule-matched options (or "none"), (3) extract schema field values for an entity — each paired with the JSON schema the structured-call helper validates against.
- Extraction prompt instructs the model to return `{name, schema, supporting_quote}` per candidate and to be **conservative** (only things the text actually names/describes), classifying only into schemas that exist.
- Link prompt is handed the candidate, the surrounding doc context, and the rule-matched existing entities, and must return either one of the given entity ids or "no match" — it must **never invent an entity id**.
- Field prompt is handed an entity + the doc and returns values only for that schema's declared fields, only where the doc supports them.
- Each prompt keeps the schema list / entity list injected as data (not hardcoded), so it works for any vault.
Implementation Notes:
- Prompts live **in source** for now (interview); leave a comment noting per-vault override is a planned future feature so a later task knows where to hook it.
- These prompts are the primary quality lever the interview expects to iterate on heavily — keep them in one module, well-labeled, easy to diff. Don't inline them into the step functions.
- Keep prompt text presentation-agnostic — no CLI framing. The supporting_quote requirement is what powers the review TUI evidence and the persisted `mentions.quote`, so make it a required output field, not optional.

Task: Implement pipeline step: extract entities
ACs:
- A step function takes the run state (doc text + available schemas) and the LLM plumbing, calls the extract-entities prompt via the structured-call helper, and returns a list of **candidate entities** (`name`, `schema`, `supporting_quote`), added to the run state.
- Candidates classified into a schema that doesn't exist are dropped (or surfaced), never invented — only existing schemas are valid targets.
- Zero candidates is a valid result (empty list), not an error.
- The step accumulates the call's token usage into the run's usage accumulator.
- Unit/integration tests against the stub LLM: a canned extraction yields the expected candidates; an empty extraction yields an empty list; a candidate naming an unknown schema is dropped; malformed output triggers the 5-retry path (via the helper) and, if exhausted, raises.
Implementation Notes:
- One discrete LLM call — separate from linking and field extraction (solution-design: steps 2–5 are separate calls, independently retryable).
- No Click/Rich, no DB writes — this produces in-memory candidates only. It reads the schema list via the schema service/repository.
- This is step 2 of the design-doc pipeline (step 1, copy+extract-text, is the already-built `doc ingest`).

Task: Implement pipeline step: link candidates to existing entities
ACs:
- A step function, for each extracted candidate: runs the **rule-based matcher** (core task) to get candidate existing entities; if there are matches, calls the link prompt via the structured-call helper to pick the correct existing entity id or "none"; the result becomes either a proposed **link** change (to that entity, carrying the supporting quote) or, if "none"/no rule matches, a proposed **new-entity** change.
- The LLM is only ever given rule-matched ids to choose from and can only return one of those or "none" — a returned id outside the candidate set is treated as a validation failure (retryable).
- Each candidate resolves to exactly one proposed change (link *or* new entity); results are recorded in run state.
- Token usage from each link call is accumulated.
- Tests (stub LLM): a candidate with an exact/alias/normalized match + LLM "that one" → link proposal; a candidate with matches but LLM "none" → new-entity proposal; a candidate with no rule matches → new-entity proposal **without** an LLM call; an LLM-returned out-of-set id → treated as invalid and retried.
Implementation Notes:
- This is solution-design steps 3 (link) + 4 (create-new) fused into one resolution pass, which matches the interview's "link/create" review stage.
- Favor linking over creating (the old skill's conservative rule) — but the *decision* is the LLM's among rule candidates; the deterministic part is only candidate discovery.
- When there are no rule candidates, skip the LLM entirely (cost + latency win) and propose a new entity directly.

Task: Implement pipeline step: extract structured fields
ACs:
- A step function, for each **approved** linked-or-created entity, calls the field-extraction prompt via the structured-call helper and produces a proposed **field-set** change carrying values only for that schema's declared fields, tagged with the source doc id.
- Only fields the doc actually supports are proposed; the committer (separate task) is responsible for not overwriting non-empty existing values — but the step should also avoid proposing values it has no support for.
- Zero extractable fields for an entity is valid (no field-set proposal, or an empty one that the reviewer/committer skips).
- Token usage accumulated.
- Tests (stub LLM): a canned field extraction yields the expected field-set for an entity; an entity with no supported fields yields nothing; a proposed field outside the schema's declared set is rejected as invalid (retryable) — schema field set comes from the schema service.
Implementation Notes:
- This runs on the survivors of the link/create review (interview option B: field extraction operates on linked-or-created-and-approved entities), so it takes the approved set, not the raw candidate set.
- Field values are written into `entities.fields_json` via the existing entity service at commit time — **do not** populate `entity_field_values` (provenance is deferred this iteration). Still tag the proposed field-set with the source doc id in-memory so the future provenance work has it.
- One discrete LLM call per entity (solution-design step 5).

Task: Define the reviewer seam + auto-approve/dry-run behaviors (presentation-decoupled)
ACs:
- A small `Reviewer` interface (e.g. `review(changes) -> decisions`, one change at a time) is the **only** way the pipeline surfaces proposed changes for approval — the orchestrator depends on this interface, never on Click/Rich directly.
- An **auto-approve** reviewer (backing `--yes`) approves every proposed change without prompting.
- `--dry-run` semantics are defined here: proposals are produced (and, per the chosen presentation, may still be shown), but the **commit step is skipped entirely** — nothing is written. Decide and document whether `--yes` + `--dry-run` combine (interview left this to design-doc default; simplest: they compose — auto-approve, then don't commit).
- Unit tests: the auto-approve reviewer approves everything; a scripted reviewer can approve some and reject others; the seam carries enough context (the proposed change + its supporting quote/excerpt) for a caller to decide.
Implementation Notes:
- **This is the decoupling task that makes the future web app possible.** The interview is explicit: the whole agent flow will later run behind a web request/response (upload → loaders → proposed entities → Approve button). Keep the pipeline talking to `Reviewer`, so a future `WebReviewer` drops in with no pipeline changes. No Click/Rich imports in the pipeline or in this interface — only in the concrete interactive implementation (next task).
- Keep the decision model aligned with the domain proposed-change types (previous task): the reviewer annotates changes with approve/reject; no inline editing (solution-design "Human Review TUI": two actions only).

Task: Implement the interactive Rich review TUI
ACs:
- A concrete interactive `Reviewer` presents **one proposed change at a time** with enough context to decide — the source-doc excerpt / supporting quote, the affected entity, and the change payload — and offers **approve or reject** only (no inline edit), using Rich prompts (`Confirm.ask`) consistent with the existing `doc`/`schema`/`entity` confirm flows.
- It renders each of the three change kinds legibly: a new entity (schema + name + fields), a link (candidate → existing entity, with the quote), and a field-set (entity + proposed values).
- Integration test drives it via `CliRunner` with scripted stdin (or by injecting the reviewer) asserting that approving/rejecting specific changes yields the expected committed/omitted results.
Implementation Notes:
- This is the **only** place Rich is allowed to touch the agent flow — it implements the seam from the previous task. Mirror solution-design "Human Review TUI": one change at a time, two actions, no inline editing (corrections happen afterward via `forte entity edit`).
- Rich prompts (not Textual) — the review is inherently sequential, matching the established TUI choice.
- Show the supporting quote prominently; it's the whole point of quote capture — it explains *why* an entity was linked.

Task: Implement the pipeline orchestrator (stepwise state machine, option B)
ACs:
- An orchestrator (e.g. `src/forte/services/agent.py`, `process_document(root, doc_id, reviewer, dry_run, ...)`) drives the full flow: **extract → review entities → link/create → review links/creates → field-extract survivors → review field-sets → commit**, holding all state in memory.
- Between stages it calls the injected `Reviewer`; only approved items flow to the next stage (approved candidates get linked/created; approved links/creates get field-extracted).
- A step whose LLM call exhausts its 5 retries aborts the whole run with a typed error and **commits nothing**; a step that returns zero results skips cleanly forward.
- On `--dry-run`, every stage runs but the commit is skipped.
- The orchestrator has **no Click/Rich imports** — it takes an `LLMClient`, a `Reviewer`, and vault root; it returns a result object (committed changes, failures, accumulated usage) the CLI renders.
- Integration tests (stub LLM + scripted reviewer) cover the happy path end-to-end, a mid-run step failure aborting with nothing written, a zero-result step, and dry-run writing nothing.
Implementation Notes:
- This is the design-doc's "Service layer … owns the multi-step ingest flow", implemented as option B (review between steps) with option-B's in-memory state (no `ingest_changes`, no resume) — the deliberate simplification from the interview.
- Order matters for cost: never run field extraction on a rejected/duplicate candidate — that's the whole reason for stepwise (option B) over generate-all-then-review.
- Returning a plain result object (not printing) is what lets `agent process`, `agent ingest`, and the future web handler all reuse this. The mechanical `doc ingest` is assumed already done (the command wires it up front), so an abort here leaves a harmless already-ingested doc.

Task: Implement best-effort commit + successes/failures reporting
ACs:
- A commit step takes the approved proposed changes and writes them through the **existing service layer** — new entities via `entity.add_entity`, field-sets via `entity.edit_entity` (only setting empty fields, never overwriting non-empty ones), and links via `document.link_document` (which persists the `mentions` row **including the supporting quote**).
- Commit is **best-effort, not atomic**: each change is attempted independently; a failure on one is recorded and the rest proceed. The step returns a structured record of successes and failures.
- Mentions persist the LLM-cited `quote` (the `mentions`/`MentionRepository.add` path already accepts a quote — thread it through; `link_document` currently passes no quote, so extend the service path to carry it for agent-created links).
- Integration tests: approved new-entity + link + field-set all land (entity files on disk, `entities`/`mentions` rows present, `mentions.quote` populated); a forced failure on one change is reported while the others still commit; field-set does not overwrite a pre-existing non-empty field.
Implementation Notes:
- Reuse the existing dual-write repositories via the service layer — do **not** write markdown/SQLite directly, so the markdown + SQLite invariant holds (the whole reason the old skill went through the CLI).
- `document.link_document` today hardcodes an empty quote path; add a way for the agent commit to pass the captured quote into `MentionRepository.add(doc_id, entity_id, quote)` (the repo already supports it). Keep the manual `doc link` command's behavior unchanged (empty quote).
- Do **not** populate `entity_field_values` — provenance deferred; field values go into `entities.fields_json` via `edit_entity`.
- "Only fill empty fields, never overwrite non-empty" mirrors the old skill's conservative rule and the PRD's edit-safety intent.

Task: Implement cost/usage reporting
ACs:
- At the end of a run, the CLI prints a concise usage summary: total input tokens, output tokens, (cache tokens if available), and an **estimated cost** for the run, derived from the run's model and a small per-model price table (e.g. `claude-haiku-4-5` at $1/$5 per 1M input/output).
- The estimate is clearly labeled as an estimate; unknown-model pricing degrades gracefully (report tokens without a dollar figure rather than erroring).
- Unit test: given a known token total and model, the reported cost matches the expected arithmetic; an unknown model reports tokens with no crash.
Implementation Notes:
- The usage accumulator (domain-models task) already sums per-call usage across the run — this task consumes it and formats the summary.
- Keep the price table small and in one place, easy to update as models/prices change. This is a "reasonable per-doc cost" NFR aid, not a billing system — no need for precision beyond the sticker rate.
- Formatting/printing lives in the CLI layer (the orchestrator returns the numbers), consistent with the presentation-decoupling rule.

Task: Wire `forte agent process <doc-id>` command and the `agent` group
ACs:
- `forte.cli` gains an `agent` Click **group** under `main`, and a `process` subcommand: `forte agent process <doc-id> [--yes] [--dry-run]`.
- Resolves the vault via `find_vault_root`, loads config (model + API key) via the config reader, constructs the real `LLMClient`, picks the reviewer (auto-approve for `--yes`, interactive Rich otherwise), calls the orchestrator, and renders the result: per-change successes/failures summary + the cost/usage line. Exits 0 on success.
- Errors map to non-zero exits with clear messages: outside a vault (shared discovery error), non-existent doc-id, missing API key (from config), and a run-aborting step failure (nothing committed).
- Integration test (stub LLM injected, `CliRunner` + isolated vault): `init` → `schema add` → `doc ingest` → `agent process <id> --yes` and assert entities/mentions landed and a summary printed; a second test asserts `--dry-run` writes nothing; a third asserts a bad doc-id exits non-zero.
Implementation Notes:
- Thin driver, mirroring the existing `doc`/`entity` command pattern: `try/except` mapping typed service errors to `click.ClickException`. No business logic here.
- The command must be able to run with an **injected stub LLM** in tests (e.g. a construction seam / factory) so the whole suite stays deterministic and free — this is the integration-first, stubbable-boundary testing approach from solution-design.
- `--yes` selects the auto-approve reviewer; interactive Rich reviewer is the default; `--dry-run` sets the orchestrator's dry-run flag. Confirm `--yes` + `--dry-run` compose per the reviewer-seam task's decision.

Task: Wire `forte agent ingest <path>` convenience wrapper
ACs:
- `forte agent ingest <path> [--yes] [--dry-run]` runs the mechanical `doc ingest` (copy + text-extract + register) and then `agent process` on the resulting doc id, in one command.
- On a re-ingest no-op (same path + content hash), it continues with the existing doc id rather than erroring (duplicate-ingest is already harmless).
- `--yes` / `--dry-run` flow through to the process stage. Errors from either stage map to non-zero exits; a Ctrl-C/abort after ingest leaves the doc ingested but uncommitted (acceptable, documented).
- Integration test: `agent ingest <file> --yes` on a fresh `.md` file both ingests the doc and lands approved entities/mentions in one shot.
Implementation Notes:
- This is purely a wrapper over the existing `ingest_document` service call + the `agent process` orchestrator — no new pipeline logic. It's the "zero-effort user" entry point from the interview.
- Do the mechanical ingest **up front** (before any LLM work) so a mid-run failure leaves a clean, re-runnable already-ingested doc — matches the interview's best-effort/duplicate-ingest reasoning.
- One doc at a time — no batch/folder flag this iteration (explicitly deferred).

Task: Remove the `ingest` skill
ACs:
- The `ingest` Claude Code skill (`.claude/skills/ingest/`) is deleted; nothing in the repo references it.
- Any docs/README pointers that described the skill-driven ingest flow are updated to point at `forte agent process` / `forte agent ingest`.
Implementation Notes:
- The interview is explicit: the skill is a one-off to throw away, "not even worth using as a reference." Do this only after `forte agent process` + `forte agent ingest` are landed and tested, so the native path fully replaces it.
- Grep for `ingest` skill references (CLAUDE.md, README, docs) before deleting so no dangling instructions remain.

# Semantic Search / RAG Foundation — Tasks

Feature: Build Forte's RAG plumbing — structure-aware chunking, local embeddings for processed docs + entity bodies, and hybrid (vector + keyword) retrieval — plus a new unified `forte search <query>` command that returns ranked results across both docs and entities. Driven by [docs/input/2026-07-21 interview-semantic-search.md](../../input/2026-07-21%20interview-semantic-search.md), [prd.md](../../prd.md), and [solution-design.md](../../solution-design.md) ("Tech Stack → Embeddings", "SQLite Schema → entity_embeddings", "Open Questions → Embedding provider").

**Command surface delivered by this feature:**
- `forte search <query>` — NEW unified ranked search over docs + entities; snippet + source (doc/entity id + link) + relevance score per result. **Replaces** the previously-spec'd (never-built) `forte entity search`.
- `forte reindex` — NEW full rebuild of chunks + embeddings + FTS for the whole vault; also the required recovery path when the configured embedding model changes.

**Key decisions locked in the interview (read before starting any task):**
- **Embedding provider = local `sentence-transformers`** (not a hosted API like Voyage) — chosen for cost, offline capability, and Forte's local-first ethos. **Gate:** a load-test task runs first to confirm resource/latency on the user's laptop before we commit the dependency.
- **What gets embedded:** processed doc text + entity markdown *bodies* only. Frontmatter / structured fields / raw source files are **excluded**.
- **Chunking is structure-aware** (split on markdown headings/paragraphs up to a max size), never naive fixed-token windows.
- **Ranking is hybrid** — vector similarity combined with SQLite FTS keyword matching — so exact-name / keyword queries aren't lost to pure semantic ranking.
- **Re-embedding is automatic on every write** that changes doc/entity content (ingest, entity edits, agent field extraction). No separate manual reindex step for normal operation; `forte reindex` is for model changes / recovery only.
- **Model versioning:** the embedding model name/version is tracked per embedding and at the vault level. Changing the configured model marks the vault **stale** and requires a full `forte reindex` — old and new vectors are not comparable.
- **Vector storage is an OPEN item:** `sqlite-vec` was the prior solution-design assumption, but at this vault's modest scale a simpler BLOB-column + in-Python cosine similarity may be enough. **Evaluate and pick during the storage task — do not assume `sqlite-vec`.**
- **Embedding client follows the same stubbable-boundary pattern as the LLM client** (`src/forte/services/agent/_llm.py`) so chunking/search tests stay deterministic and free — never load a real model in the main suite.
- **Philosophy: don't overbuild.** Product is early-stage; build something that works reasonably well and adds no significant ongoing cost. Expect to revisit from real usage.

**Explicitly OUT OF SCOPE this pass (note in relevant tasks, do not build):**
- `forte agent ask` (LLM-generated answers with citations) — the eventual consumer, a later task.
- Wiring entity embeddings into the ingest pipeline's entity-linking candidate discovery — deferred (needs entity-only results).
- A `--type` filter to restrict `forte search` to docs-only / entities-only / both — needed later (partly for the entity-linking use case above), not now.
- Result pagination specifics — implementation judgment (e.g. top 10, no pagination).

---

- Spike: load-test `sentence-transformers` on the target laptop (gate)
- Write `forte search` behavior spec
- Add embedding configuration to the config service
- Design & build the index storage schema (chunks + embeddings + FTS + model version)
- Build the embedding client abstraction with a stubbable boundary
- Implement the structure-aware chunker (core, deterministic)
- Build the index repository (write + read chunks / embeddings / FTS)
- Implement hybrid retrieval + ranking (vector + keyword)
- Implement the search service (query → ranked results)
- Wire automatic re-embedding into content writes
- Implement model-version staleness detection + `forte reindex` command
- Wire `forte search <query>` command + result display; retire `forte entity search`

---

Task: Spike — load-test `sentence-transformers` on the target laptop (gate)
ACs:
- A short throwaway script (or notebook under `docs/impl/2026-07-21/`) embeds a synthetic corpus of **thousands of doc/entity-sized text chunks** with a candidate `sentence-transformers` model on the user's laptop, CPU-only, and records: first-run model download size, peak RAM, bulk re-embed wall time for the whole corpus, and single-query embed + search latency.
- Results are written up in a short findings doc (`docs/impl/2026-07-21/embedding-load-test.md`) with a clear go/no-go against the bar: **thousands of docs/entities, few-seconds-or-better search latency, no heavy resource use**.
- The write-up names the **specific model** to standardize on (e.g. `all-MiniLM-L6-v2` ≈ 80MB, vs a `bge-base`/`mpnet` class model) and its embedding dimension, since downstream schema/storage tasks need the vector width.
Implementation Notes:
- This is the interview's explicit **prerequisite gate** before committing to the `torch`/`sentence-transformers` dependency — run it first. If it fails the bar, stop and re-open the provider decision rather than proceeding.
- Reference numbers to sanity-check against (from the interview's informational answer): MiniLM-L6-v2 is ~80MB, CPU embeds short text in milliseconds; bulk re-embed of hundreds–low-thousands of items is seconds to low-minutes on CPU. Main costs are the `torch` dependency footprint and the one-time model download.
- Keep it genuinely throwaway — no production code here. Its only durable output is the findings doc and the chosen model + dimension, which the schema, config, and embedding-client tasks consume.

Task: Write `forte search` behavior spec
ACs:
- A new spec file `docs/spec/forte-search.md` exists, following the structure of `docs/spec/forte-doc.md` (title + short intro, `## Scenarios` with Gherkin blocks, `## Out of scope`).
- Scenarios cover, at minimum, observable CLI behavior (stdout, exit code) against a **stubbed embedding client**:
  - `forte search <query>` in a vault with indexed docs + entities returns a ranked list where each result shows a **snippet**, its **source** (doc or entity, with the integer id / link), and a **relevance score**.
  - Results are **unified**: a single query can return both doc chunks and entity-body chunks, interleaved by rank.
  - A **hybrid** win: an exact-name / keyword query surfaces the keyword-matching item even when pure vector similarity would rank it lower (assert the keyword hit appears).
  - Empty vault / no matches → a clean "no results" message, exit 0.
  - `forte search` outside a vault → shared "Not inside a Forte vault" error, non-zero exit, no side effects.
  - Running `forte search` when the vault is **stale** (configured embedding model differs from the indexed one) → a clear message telling the user to run `forte reindex`, non-zero (or clearly-degraded) exit — cross-reference the staleness task.
- The spec documents the result **ordering/relevance contract** at a behavioral level (higher score = better; ties broken deterministically) without pinning the exact scoring math.
- `docs/spec/forte-entity.md` is updated: the deferred `forte entity search` note (currently line ~229) is replaced with a pointer stating entity search is **superseded by the unified `forte search`** in `forte-search.md`.
Implementation Notes:
- Specs are the source of truth per CLAUDE.md and drive the integration tests written in the command/service tasks. Write this first (after the spike).
- Tests must be deterministic and free — every scenario runs against the **stubbed embedding boundary**, never a real model. State explicitly that live-model latency/quality checks (the spike) are kept out of the main suite (matches solution-design "Testing").
- Put explicitly **out of scope** in the spec: `forte agent ask`, the `--type` docs/entities filter, entity-linking candidate discovery via embeddings, and pagination specifics.

Task: Add embedding configuration to the config service
ACs:
- `src/forte/services/config.py` `Config` gains an **embedding model** field (name/version string, e.g. `sentence-transformers/all-MiniLM-L6-v2`) with a sensible default matching the spike's chosen model, read from `.forte/config.yaml` (e.g. `embedding.model`).
- `write_default_config` is updated to lay down the `embedding` section alongside the existing `model` / `api_keys` blocks; `forte init` tests updated to match.
- `load_config` returns the configured embedding model (default when unset), tolerant of unknown keys, consistent with the existing reader's style.
- Unit tests cover: default embedding model when unset, explicit override, and that unknown/extra keys don't break parsing.
Implementation Notes:
- Keep this in the **service layer** — the embedding client and the staleness check both read the model id through `load_config`, never `os.environ` or ad-hoc YAML reads.
- Local `sentence-transformers` needs **no API key**, so unlike the anthropic key there's no `require_*`-style error here — a missing embedding config just falls back to the default model.
- The model **string is the version** for staleness purposes (interview: "track model name/version"). Keep it a single canonical string so the staleness task can compare it byte-for-byte against what's stored in the index.

Task: Design & build the index storage schema (chunks + embeddings + FTS + model version)
ACs:
- The SQLite bootstrap (`src/forte/db/schema.py`) is extended (the `entity_embeddings` deferral comment there is resolved) to support chunk-level search over both sources. At minimum:
  - A **chunks** table: `id`, `source_type` (`'doc'` | `'entity'`), `source_id` (the doc/entity integer id), `chunk_index`, `text`, and the stored **embedding**.
  - A **keyword index**: an FTS5 virtual table over chunk `text` (with the doc/entity ids retrievable) for the keyword half of hybrid ranking.
  - **Model-version tracking**: the embedding model string stored per embedding (or per chunk) **and** a vault-level record of the model the index was last built with (e.g. a `meta`/`index_state` row) so the staleness task can compare.
- The **vector storage approach is decided in this task** — evaluate `sqlite-vec` vs. a plain BLOB column + in-Python cosine similarity, and pick the simpler option that meets the modest-scale bar. Document the decision (1–2 lines in the schema module + a note in solution-design "Open Questions" resolving the item).
- Fresh `forte init` vaults get the new tables; `test_db_schema.py` is updated to assert their presence.
- The embedding vector width matches the spike's chosen model dimension.
Implementation Notes:
- Interview is explicit that `sqlite-vec` is **not** locked in — at hundreds-to-low-thousands of chunks, a BLOB column of float32 bytes + brute-force cosine in Python is likely simpler, dependency-free, and fast enough. Favor that unless the spike shows otherwise; leave a comment noting `sqlite-vec` as the swap-in if scale grows. Don't overbuild.
- Only **processed doc text and entity bodies** are chunked/embedded — the schema stores chunks of those, never frontmatter or raw files.
- There is no ALTER/migration framework at MVP (dual-write, fresh DBs via `initialize_database`) — extend the DDL list in place; existing vaults are re-created or reindexed, not migrated.
- Keep the model-version columns first-class now even though only one model exists — it's the cheap enabler for the staleness/reindex requirement and avoids a schema change later.

Task: Build the embedding client abstraction with a stubbable boundary
ACs:
- A new module (e.g. `src/forte/services/embedding.py`) defines a narrow `EmbeddingClient` protocol whose single method embeds a batch of texts and returns their vectors (list of float vectors), mirroring the `LLMClient` protocol shape in `src/forte/services/agent/_llm.py`.
- A **real** implementation wraps `sentence-transformers` (added to `pyproject.toml`), constructed with the model id from config, lazy-loading the model on first use so importing the module (and the rest of the CLI) doesn't pull `torch` until an embedding is actually needed.
- A **stub** implementation returns caller-supplied canned vectors (or a cheap deterministic hash-based pseudo-embedding) per call, so chunking/search/re-embed tests run deterministically and free without loading a model.
- The client exposes the **model id / dimension** it produces, so callers can tag stored embeddings with the version and assert width.
- Unit tests: the stub returns queued/deterministic vectors in order; the real client's construction (model wiring, lazy load) is covered but **no real model load runs in the main suite**.
Implementation Notes:
- Follow the exact stubbable-boundary pattern already established for the LLM (`LLMClient` / `AnthropicLLMClient` / `StubLLMClient`) — same file layout, docstring rationale, and injection seam. This is the interview's explicit ask ("stub the embedding client").
- **Lazy-load `torch`/`sentence-transformers`** — deterministic commands (`init`, `schema`, `doc list`, etc.) must not pay the import cost or require the model download. Only search + re-embed paths touch the real client.
- Batch the encode call (sentence-transformers encodes lists efficiently) — the re-embed and reindex paths will hand it many chunks at once.
- Keep it presentation-decoupled (no Click/Rich) — service-layer infrastructure the future `agent ask` and web layer reuse verbatim.

Task: Implement the structure-aware chunker (core, deterministic)
ACs:
- A **deterministic, non-LLM** chunker (core `forte`, e.g. `src/forte/services/chunking.py`) takes a markdown/plain-text body and splits it **structure-aware**: on markdown headings / paragraph boundaries, packing content up to a **max chunk size** without splitting mid-paragraph where avoidable (oversized single paragraphs get hard-split as a fallback).
- Given an entity body or a processed-doc body, it returns an ordered list of chunk texts (with stable `chunk_index`) ready for embedding + storage.
- Empty / whitespace-only input yields zero chunks (valid, not an error).
- It operates on the **body only** — callers pass already-extracted body text (entity markdown body via `entity_markdown`, processed-doc body via `document_markdown`); the chunker never sees or emits frontmatter.
- Unit tests cover: a multi-heading doc split into the expected sections, a single long paragraph exceeding max size hard-split, a short body → one chunk, and empty → no chunks. Fully deterministic, no client needed.
Implementation Notes:
- Structure-aware, **not** fixed-token windows (interview). Split on `#` headings and blank-line paragraph breaks; only fall back to a size-based hard split for a single oversized block.
- Keep it a pure function of `(text, max_size) -> list[str]` so it's trivially testable and reused identically for both docs and entities. Size in characters (or a cheap token proxy) is fine at this stage — don't pull in a heavyweight tokenizer.
- This feeds the index repository and re-embed paths; keep it free of DB/embedding imports.

Task: Build the index repository (write + read chunks / embeddings / FTS)
ACs:
- A repository (e.g. `src/forte/db/index_repository.py`, matching the existing `*_repository.py` style) owns all reads/writes of the chunks + embeddings + FTS tables:
  - `reindex_source(source_type, source_id, chunks_with_vectors, model_id)` — **replace** all existing chunks/embeddings/FTS rows for a given doc or entity with the new set, in one transaction (so re-embedding on edit is idempotent and leaves no stale chunks).
  - `delete_source(source_type, source_id)` — drop all index rows for a removed doc/entity.
  - Read helpers the retrieval layer needs: fetch all `(chunk_id, source_type, source_id, embedding)` for vector scan, and an FTS keyword query returning matching chunk ids/rows.
  - Get/set the vault-level **index model version** (for staleness).
- The FTS virtual table is kept in sync with the chunks table on every write/delete.
- Integration tests (real temp SQLite): reindex a source then re-reindex with different text and assert old chunks are gone; delete a source and assert its chunks + FTS rows vanish; the vector-scan and FTS reads return the expected rows.
Implementation Notes:
- Mirror the dual-write discipline — but note **chunks/embeddings are derived index data, not source of truth** (like `docs/processed/`), so they live only in SQLite, not as extra markdown files. The markdown bodies remain authoritative.
- "Replace, don't append" is the key invariant: an entity edit shrinking its body must not leave orphaned chunks. Do the delete+insert in a single transaction.
- Store embeddings in whatever column type the schema task chose (BLOB float32 bytes or `sqlite-vec` column); keep serialization (vector ↔ bytes) in one helper here.

Task: Implement hybrid retrieval + ranking (vector + keyword)
ACs:
- A retrieval function takes a query embedding **and** the raw query string, and returns a ranked list of chunk hits by combining: (a) **vector similarity** (cosine) over stored embeddings, and (b) **SQLite FTS keyword** matches — so exact-name/keyword queries aren't lost to pure semantic ranking (interview's hybrid requirement).
- The two signals are merged into a single ordered result set with a **combined relevance score** and deterministic tie-breaking; the fusion method (e.g. reciprocal-rank fusion or a weighted normalize-and-sum) is documented in one place and easily tunable.
- Returns the top-N chunks (default decided in build, e.g. 10) each carrying source_type, source_id, chunk text, and score — enough for the service to assemble a result line.
- Unit/integration tests (deterministic vectors from the stub + a real FTS table): a query whose keyword exactly matches one item ranks that item at/near the top even if another item is a closer vector match; a purely semantic query ranks by vector similarity; ties break deterministically.
Implementation Notes:
- Keep the fusion simple and legible — at this scale a brute-force cosine over all stored vectors in Python plus an FTS `MATCH` query, merged by rank, is plenty. Don't overbuild an ANN index.
- This is the piece that most directly delivers the "hybrid" interview decision — make the keyword contribution observable/testable, not a token afterthought.
- Pure function of (query vector, query text, index reads) → ranked hits; no Click/Rich, no embedding-model load (the query is embedded by the caller/service).

Task: Implement the search service (query → ranked results)
ACs:
- A service entrypoint (e.g. `src/forte/services/search.py`, `search(root, query, limit=...) -> list[SearchResult]`) ties it together: load config → embed the query via the `EmbeddingClient` → run hybrid retrieval → resolve each hit back to its source (doc/entity id, name/link) → build `SearchResult` objects carrying **snippet + source + score** (the interview's result contract).
- The snippet is the matching chunk text (trimmed to a readable length), in the spirit of how `mentions` surface a supporting quote.
- Before searching, it checks vault **staleness** (configured model vs indexed model) and raises a typed error the CLI turns into the "run `forte reindex`" message (cross-references the staleness task).
- Results unify docs + entities in one ranked list; empty index / no matches returns an empty list (not an error).
- The `EmbeddingClient` is **injectable** so integration tests drive it with the stub.
- Integration tests (stub embeddings, real vault): indexed docs + entities → a query returns interleaved results with populated snippet/source/score; no matches → empty; stale vault → typed error.
Implementation Notes:
- This is the reusable retrieval capability a future `forte agent ask` will call to gather context — keep it presentation-decoupled (return `SearchResult` objects; the CLI formats them), same discipline as the agent orchestrator returning a result object.
- `SearchResult` should expose everything the CLI needs to render one line: source_type, source_id, display name / link target, snippet, score.
- Default `limit` (e.g. 10) is an implementation call per the interview — pick a sane default, no pagination this pass.

Task: Wire automatic re-embedding into content writes
ACs:
- Every write that changes embeddable content triggers a **re-chunk + re-embed + index replace** for the affected source, with no separate manual step:
  - Entity create/edit (`entity.add_entity`, `entity.edit_entity`) → re-index that entity's body.
  - Entity remove (`entity.remove_entity`) → `delete_source` for it.
  - Doc ingest / processed-text write (`document.ingest_document`) → re-index that doc's processed body; doc remove → `delete_source`.
  - Agent field extraction / commit (`services/agent/_commit.py`) writes that change an entity body → re-index (it already goes through the entity service, so ideally this is covered by hooking the service layer once).
- Re-embedding uses the injected `EmbeddingClient` so the whole existing test suite stays deterministic/free — wiring it must not force a real model load in tests (inject the stub, or make the client optional/lazy so non-search tests are unaffected).
- Integration tests: editing an entity's body then `forte search` finds the new text and not the old; removing an entity drops it from results; ingesting a doc makes its body searchable.
Implementation Notes:
- Interview: "Automatic on write." Hook at the **service layer** (where the dual-write already happens) so both the CLI and the agent pipeline get re-embedding for free — the agent commit already writes entities via the entity service, so a single well-placed hook covers ingest + manual edits + agent writes.
- Frontmatter/field-only changes that don't alter the **body** ideally skip re-embedding (only body text is embedded) — at minimum, re-embedding on any entity write is acceptable for MVP; note the optimization but don't overbuild.
- The existing large test suite must keep passing without network/model access — this is the main risk of this task. Provide a null/stub embedding client by default in tests (e.g. via the same construction seam the agent uses for its stub LLM), and keep re-embed failures from breaking the primary markdown+SQLite write (log/skip, since the index is derived data).

Task: Implement model-version staleness detection + `forte reindex` command
ACs:
- A staleness check compares the **configured** embedding model (from `load_config`) against the model recorded in the index's vault-level version row; a mismatch (or an unbuilt index) marks the vault **stale**.
- `forte reindex` rebuilds the entire index from scratch: drop all chunks/embeddings/FTS, then re-chunk + re-embed **every** processed doc body and entity body with the currently-configured model, and stamp the index model-version row to match. Prints progress/summary, exits 0.
- After a model change in config, `forte search` reports staleness and directs the user to `forte reindex` (the behavior the spec pins); after `reindex`, search works against the new model.
- Integration tests: change the configured model → search reports stale; `forte reindex` → search works and the stored version matches config; reindex on an empty vault is a clean no-op.
Implementation Notes:
- Interview: "Track model name/version, require full reindex on change." Normal writes re-embed incrementally with the *current* model; `reindex` is specifically for the model-changed / rebuild-from-source case — old and new vectors aren't comparable, so a partial mix is invalid.
- Reuse the chunker + embedding client + index repository already built — `reindex` is an orchestration over `reindex_source` for the full corpus (enumerate via `DocumentRepository.list()` + `EntityRepository.list()`), not new indexing logic.
- This is also the natural recovery command if the derived index is ever lost or corrupted (it's rebuildable from the authoritative markdown). Keep it idempotent.

Task: Wire `forte search <query>` command + result display; retire `forte entity search`
ACs:
- `forte.cli` gains a top-level `search` command: `forte search <query>` — resolves the vault via `find_vault_root`, constructs the real `EmbeddingClient` from config, calls the search service, and renders each result as a line showing **snippet + source (doc/entity id + link) + relevance score**, consistent with existing Rich output style.
- No matches → a clear "no results" message, exit 0. Outside a vault → the shared discovery error, non-zero. Stale vault → the "run `forte reindex`" message from the staleness task, mapped to a clean non-zero (or clearly-degraded) exit.
- The command is testable with an **injected stub embedding client** (construction seam mirroring the agent command's stub-LLM injection) so integration tests are deterministic and free.
- `forte entity search` is **not** added (it was spec'd but never implemented — see `forte-entity.md`); the unified `forte search` is its replacement. Any doc/help/README pointer to `entity search` is updated to `forte search`.
- Integration tests (`CliRunner` + isolated vault + stub embeddings): `init` → `schema add` → ingest a doc + add entities → `forte search <term>` returns ranked snippet/source/score lines; a no-match query prints the empty message; outside-vault exits non-zero.
Implementation Notes:
- Thin driver mirroring the existing `doc`/`entity`/`agent` command pattern: `try/except` mapping typed service errors (including the staleness error) to `click.ClickException`; no business logic here — formatting only.
- Result line spirit: like `mentions` show a supporting quote, each search hit shows its snippet as evidence plus where it came from and how strongly it matched.
- Since `forte entity search` was never built, "retire" is a **spec/doc** change, not code removal — confirm via grep that no command or test references it before considering this done.

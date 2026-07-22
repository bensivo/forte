# Interview - Semantic Search / RAG Foundation

**Topic:** Chunking, embeddings, and retrieval to support a unified `forte search` command (and, eventually, `forte agent ask`)
**Interviewee:** Ben Sivoravong
**Date:** 2026-07-21

## Summary

- **Scope for this task:** build the RAG plumbing — structure-aware chunking, embeddings for doc chunks and entity bodies, hybrid (vector + keyword) retrieval — plus a new unified `forte search <query>` command that returns ranked results across both docs and entities. `forte agent ask` (LLM-generated answers with citations) is explicitly a later task, not part of this pass.
- `forte search` **replaces** the previously spec'd `forte entity search` command.
- **Embedding provider:** local `sentence-transformers`, chosen over hosted APIs (e.g. Voyage) for cost, offline capability, and fit with Forte's local-first CLI ethos. A load-test task should run first to confirm resource usage and latency on the user's laptop at a scale of thousands of docs/entities, with the target of a few-seconds-or-better search latency.
- **What gets embedded:** processed doc text and entity markdown bodies. Frontmatter/structured fields and raw source files are excluded.
- **Chunking strategy:** structure-aware (split on markdown headings/paragraphs up to a max size), not naive fixed-token windows.
- **Ranking:** hybrid — vector similarity combined with SQLite FTS keyword matching — so exact-name/keyword queries aren't lost to pure semantic ranking.
- **Re-embedding:** automatic on every write that changes doc/entity content (ingest, entity edits, field extraction) — no separate manual reindex step needed for normal operation.
- **Model versioning:** the embedding model name/version is tracked per embedding; changing the configured model marks the vault stale and requires a full reindex.
- **Vector storage:** `sqlite-vec` was the prior default assumption in solution-design.md, but should be re-evaluated against simpler alternatives (e.g. BLOB storage + cosine similarity in Python) given the vault's modest scale — open item, not locked in.
- **Result display:** each `forte search` result shows a matching snippet, its source (doc or entity, with ID/link), and a relevance score — similar in spirit to how `mentions` already show a supporting quote.
- **Testing:** the embedding client follows the same stubbable-boundary pattern as the LLM client, so chunking/search tests stay deterministic and fast.
- **Explicitly deferred (not this task):**
  - Wiring entity embeddings into the ingest pipeline's entity-linking step (candidate discovery) — deferred because that use case needs entity-only results, which ties into the next point.
  - A `--type` filter on `forte search` to restrict results to entities-only, docs-only, or both — needed later (partly to support the entity-linking use case above), not required for this pass.
  - Result count/pagination details — left to implementation judgment (e.g. top 10 by default).
- **Philosophy for this pass:** the product is early-stage — build something that works reasonably well and doesn't add significant ongoing cost, rather than over-engineering; expect to revisit based on real usage.

## Interview Log

Q: To confirm scope: we're interviewing about building the semantic search / RAG foundation (chunking, embeddings for chunks + entities, retrieval) that a future 'forte agent ask' will sit on top of. Are there any existing docs beyond what's in docs/ (e.g. notes, spike results, external references) I should review before we start?
A: You can look at solution-design.md for general info on how this app is built, but we didn't actually mention that feature much in it.

Q: What's actually in scope for this task? You mentioned 'forte agent ask' is the eventual goal, but described the immediate need as chunking, embeddings, and retrieval.
A: Mostly the RAG plumbing right now. Actually, lets build a 'forte search' piece too just to make sure we have an effective search engine. And because a search engine is just generally going to be useful anyways.

Q: solution-design.md lists the embedding provider as an open spike (local sentence-transformers vs. hosted API like Voyage). Has that spike happened, or should we decide it now as part of this task?
A: How heavy is sentence-transformers? Would most people be able to run it locally on a laptop?

Q: [factual answer, not part of interview options] sentence-transformers is quite light for common models — all-MiniLM-L6-v2 is ~80MB, runs fine on CPU on any modern laptop, embeds short text in milliseconds, no GPU needed. Larger models (bge-base, mpnet) are still a few hundred MB and run acceptably on CPU. Main cost is the torch dependency and first-run model download. For a personal vault (hundreds to low-thousands of docs/entities), bulk re-embedding the whole vault would take seconds to low minutes on CPU.
A: (n/a — informational)

Q: Given that sentence-transformers is lightweight enough for a laptop, which way do you want to go for the embedding provider?
A: Lets do sentence-transformers, but lets note down to do a task to do a basic load-test of it on my laptop before committting to it. I want ot make sure it doesn't consume a ton of resources, and that the results are fast enough on my laptop.

Q: What should get chunked and embedded? (Recall: docs have raw + processed markdown with frontmatter; entities have frontmatter fields + a free-form markdown body.)
A: Processed docs + entity bodies.

Q: How should chunking actually split the text — what strategy and size?
A: Structure-aware (paragraph/section splitting).

Q: What should `forte search <query>` actually search over and return?
A: Unified: docs + entities together.

Q: Should ranking be pure vector similarity, or hybrid (combine with keyword/exact-match signals)?
A: Hybrid (vector + keyword/FTS).

Q: When does (re-)embedding happen — doc/entity content changes over time (ingest, edits, new fields extracted)?
A: Automatic on write.

Q: What should a `forte search` result line show to the user?
A: Snippet + source + score.

Q: solution-design.md's testing philosophy puts the LLM behind a stubbable boundary so ingest tests are deterministic. Should embeddings follow the same pattern?
A: Yes, stub the embedding client.

Q: If the embedding model ever changes (e.g. upgrading to a better sentence-transformers model later), old and new embeddings aren't comparable. How should that be handled?
A: Track model name/version, require full reindex on change.

Q: For the sentence-transformers load-test task you flagged earlier — what scale/latency should it validate against? This sets the bar for 'fast enough' and 'not too heavy.'
A: Thousands of docs/entities, few-second search OK.

Q: solution-design.md tentatively named `sqlite-vec` for the vector column. Any reason to reconsider, or should we lock that in as part of this task?
A: Reconsider — evaluate alternatives too.

Q: The existing spec already documents `forte entity search <query>` (entity-only). Now that we're adding a unified `forte search <query>` (docs + entities), what happens to `forte entity search`?
A: Replace it with unified `forte search`.

Q: The entity-linking step (ingest pipeline step 3) currently does exact/normalized name matching, with 'vector similarity over name + aliases' noted as a future enhancement. Should this task also wire embeddings into entity linking, or keep that separate?
A: We'll do it later, because when we want to do that, we only want to return entities, not docs and entities. So one feature we'll also need to add (also later) is a way to restrict your search to only entities, only docs, or both.

Q: Any preference on default result count / pagination for `forte search`, or is that a minor implementation detail we can decide during build (e.g. top 10, no pagination for now)?
A: Fine to decide during build.

Q: Anything else important for this RAG/search feature that we haven't covered — timeline, priority relative to other in-flight work, or constraints I should know about?
A: We're in early phases of this product, so don't overbuild. Just get something that works reasonably well right now, and doens't add a ton of huge cost, and we'll shore it up later with new feature requests.

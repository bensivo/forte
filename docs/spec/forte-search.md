# `forte search` Spec

Behavior spec for the `forte search <query>` command — a unified, ranked search over a vault's indexed **documents** and **entities**. It combines vector similarity over embedded chunks with SQLite FTS keyword matching (a **hybrid** retrieval strategy), so exact-name / keyword queries surface reliably alongside semantically-related content. Documents are chunked from their processed body text (`docs/processed/`); entities are chunked from their markdown body (the free-form text below the frontmatter). Frontmatter and structured fields are never embedded or searched by this command. Every scenario here runs against a **stubbed embedding client** with deterministic, canned vectors — no real model is loaded, keeping these tests free and reproducible; live-model quality and latency are covered separately by the load-test spike (`docs/impl/2026-07-21/embedding-load-test.md`) and are not part of this suite. This command operates on an existing vault, discovered git-style by walking up from the current working directory to find a `.forte/` directory.

## Result ordering / relevance contract

- Each result carries a **relevance score**; higher is always better. The score is a fused signal (vector similarity plus keyword match strength) — its exact formula is deliberately not pinned here, so it may change as ranking is tuned.
- Results are returned in **descending score order**, one ranked list spanning both docs and entities — there is no separate "docs" and "entities" section.
- Ties in score are broken **deterministically** (the same query against the same index always returns results in the same order), but the specific tie-break rule is an implementation detail, not asserted here beyond "stable and repeatable."

## Scenarios

### Scenario: Search a vault with indexed docs and entities

```gherkin
Given the current working directory is inside a Forte vault
And a document has been ingested and indexed
And an entity has been added with a markdown body and indexed
And the embedding client is stubbed with deterministic vectors
When the user runs `forte search "some query"`
Then the process prints a ranked list of results
And each result shows a snippet of the matching text
And each result shows its source: either a document with its integer id and a link/path, or an entity with its integer id and a link/path
And each result shows a relevance score
And the process exits with status code 0
```

### Scenario: Results unify docs and entities in one ranked list

```gherkin
Given the current working directory is inside a Forte vault
And a document is indexed whose processed text is relevant to the query
And an entity is indexed whose markdown body is relevant to the same query
And the embedding client is stubbed so both the doc chunk and the entity chunk score highly
When the user runs `forte search "shared topic"`
Then both the document result and the entity result appear in the single printed list
And they are interleaved by rank rather than grouped into separate "documents" and "entities" sections
And the process exits with status code 0
```

### Scenario: A hybrid win — keyword match surfaces despite weaker vector similarity

```gherkin
Given the current working directory is inside a Forte vault
And an entity named "Acme Corp" is indexed, whose stored chunk contains the exact text "Acme Corp"
And another indexed chunk is stubbed to have a higher pure vector-similarity score for the query than the "Acme Corp" chunk
And the query text itself contains the exact keyword "Acme Corp"
When the user runs `forte search "Acme Corp"`
Then the result for the "Acme Corp" chunk appears in the printed results
And its presence is due to the keyword (FTS) match, not pure vector similarity alone
And the process exits with status code 0
```

### Scenario: Empty vault or no matches

```gherkin
Given the current working directory is inside a Forte vault
And no documents or entities have been indexed (or none match the query)
When the user runs `forte search "nothing relevant"`
Then the process prints a clean message indicating no results were found
And the process exits with status code 0
```

### Scenario: Search outside a vault

```gherkin
Given the current working directory is not inside a Forte vault
And no `.forte/` directory exists in the current directory or any ancestor
When the user runs `forte search "anything"`
Then the process prints an error message indicating the user is not inside a Forte vault
And the process exits with a non-zero status code
And no search is performed and no output is produced beyond the error
```

### Scenario: Vault index is stale (configured embedding model changed)

```gherkin
Given the current working directory is inside a Forte vault
And the vault was previously indexed with one embedding model
And the vault's configured embedding model (in `.forte/config.yaml`) has since been changed to a different model
When the user runs `forte search "anything"`
Then the process prints a clear message explaining the index is stale and instructing the user to run `forte reindex`
And the process exits with a non-zero (or otherwise clearly-degraded) status code
And no ranked results are printed
```

## Out of scope

- **`forte agent ask`** — LLM-generated answers with citations built on top of search results is a later, separate command.
- **A `--type` filter** — restricting results to docs-only or entities-only is not implemented in this batch; `forte search` always searches both.
- **Entity-linking candidate discovery via embeddings** — using entity embeddings to propose entity-linking candidates during doc ingest is a separate, deferred feature.
- **Pagination specifics** — the command returns a bounded top-N list; there is no `--page`/`--limit` interface or cursor-based pagination in this batch.
- **Live-model quality and latency** — real `sentence-transformers` embedding behavior (download size, RAM, latency at scale) is covered by the one-off load-test spike, not by this deterministic spec/test suite, which always runs against a stubbed embedding client.

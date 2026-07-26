# `forte agent --bulk-commit` — Tasks

Feature: add a `--bulk-commit` flag to `forte agent ingest` and `forte agent process` that replaces the one-at-a-time approve/reject TUI with a **single text-editor session**. Instead of prompting the user per proposal, Forte writes all proposed changes into a temp file (one proposal per line, each pre-filled with a `[y]`/`[n]` action), opens the user's editor, and applies the decisions after the editor closes. Source: [docs/input/2026-07-25 commit-feature-description.md](../../input/2026-07-25%20commit-feature-description.md). Builds on the existing agent pipeline ([docs/spec/forte-agent.md](../../spec/forte-agent.md), `src/forte/services/agent/`).

**Key decisions locked with the requester (deviations from the raw feature sketch):**

1. **One editor, both review points at once.** The current pipeline has *two* interactive review points — entity proposals (new + link) and, separately, field-sets on the entities that were approved ("option B": fields are only extracted for approved entities). Bulk mode collapses both into a **single editor invocation**. This means bulk mode must **eagerly extract fields for every proposed entity up front**, before the editor opens — a deliberate cost tradeoff (more LLM calls than option B) that is intrinsic to showing everything at once. This is a **separate orchestration path**, not a drop-in `Reviewer`, because the existing `Reviewer` seam is called twice and can't combine the two batches.
2. **`[y]`/`[n]` only, not the 3-letter `[n]`/`[s]`/`[l]` scheme in the sketch.** Each line is pre-filled with `[y]` (apply the proposed change) and the user can flip it to `[n]` (skip). The user **cannot** create new records or convert new↔link inside the editor — only accept or skip what was proposed. This fits the existing approve/reject `Decision` contract exactly and honors the PRD's "no inline editing during review" rule.
3. **Sectioned layout.** The editor file is organized into sections — proposed **new entities**, then **links to existing entities**, then **field updates** — rather than one flat list.
4. **Edge case — approved field-set on a skipped entity → create the entity anyway.** If the user skips (`[n]`) a proposed new entity but approves (`[y]`) a field-update that targets that same entity, Forte creates the entity anyway so the field values have somewhere to land.
5. **Editor resolution: `$VISUAL` → `$EDITOR` → config → fallback.** Git-style. A new optional `editor` key in `.forte/config.yaml` sits between the env vars and a hardcoded fallback chain (`vi`/`nano`).
6. **Composition:** `--yes` takes precedence over `--bulk-commit` (auto-approve everything, no editor is opened). `--dry-run` composes with `--bulk-commit` (editor opens to collect decisions, but nothing is committed).

- Write `forte agent --bulk-commit` behavior spec
- Add `editor` setting to vault config
- Implement bulk-commit document format (serialize + parse)
- Implement the editor-session boundary and terminal launcher
- Implement the bulk orchestration flow
- Wire `--bulk-commit` into `agent ingest` and `agent process`

---

Task: Write `forte agent --bulk-commit` behavior spec
ACs:
- New scenarios are added to `docs/spec/forte-agent.md` (or a sibling `docs/spec/forte-agent-bulk-commit.md` if the author prefers to keep the base spec focused — pick one and note it), following the existing Gherkin style (title + intro, `## Scenarios`, `## Out of scope`), and every scenario runs against the **stubbed LLM boundary** and a **stubbed editor boundary** (no real editor is ever spawned in a test — see the editor-session task).
- Scenarios cover, at minimum:
  - `agent process <id> --bulk-commit`: the LLM is stubbed to produce a mix of new-entity, link, and field-set proposals; the (stubbed) editor receives a file containing all of them in the three sections with each line pre-filled `[y]`; the editor returns the file unchanged; all proposals are committed; exit 0.
  - Same setup, but the stubbed editor flips some lines to `[n]`: only the `[y]` proposals are committed; the `[n]` ones leave no entity/mention/field write.
  - **Deleted lines are treated as skipped**: the stubbed editor deletes a proposal line entirely; that proposal is not committed (same effect as `[n]`).
  - **Invalid/unrecognized action is treated as skipped**: a line with a garbage action token (e.g. `[x]` or empty) is not committed.
  - **Edge case**: the stubbed editor sets `[n]` on a new-entity line but `[y]` on a field-update line targeting that same new entity → the entity **is** created and the fields are applied.
  - `--bulk-commit --yes` together: **no editor is invoked** and every proposal is auto-approved and committed (yes wins).
  - `--bulk-commit --dry-run` together: the editor **is** invoked and decisions are collected, but nothing is written to `entities`/`mentions`/markdown; exit 0.
  - Editor aborts (the launcher reports the editor exited non-zero, e.g. the user did `:cq` in vim): the run aborts, **nothing is committed**, exit is non-zero, and a clear message is printed.
  - Zero proposals: the editor is **not** opened and the command reports "nothing to propose", exit 0.
  - `agent ingest <path> --bulk-commit` end-to-end: the file is ingested (a `documents` row exists) and then the same bulk flow runs against it.
- Scenarios explicitly state that `--bulk-commit` presents **all** proposals (entities *and* fields) in one editor pass, unlike the default flow's two sequential review points.
Implementation Notes:
- Specs are the source of truth per CLAUDE.md and drive the integration tests in the command/orchestration tasks — write this first so those tasks have concrete assertions.
- Keep scenarios black-box: observable behavior is (a) the text handed to the editor boundary, (b) what the editor boundary returns, and (c) resulting DB rows / markdown files / exit codes. The stubbed editor is a function `str -> str` (see editor-session task); assert on the text it receives and script its return value.
- Add to `## Out of scope`: creating brand-new entities by typing lines in the editor; converting a proposal's type (new↔link) in the editor; per-line inline field editing; and re-opening the editor to fix mistakes (a bad edit is just re-run).

Task: Add `editor` setting to vault config
ACs:
- `src/forte/services/config.py`: `Config` gains an `editor: str | None` field. `load_config` reads it from the config YAML (top-level `editor:` key, or nested under a section — pick one and document it) and defaults to `None` when absent, staying consistent with the reader's existing "tolerant, defaults over raising" behavior.
- `DEFAULT_CONFIG_CONTENT` documents the key with a commented-out example (e.g. `# editor: vim`) so a freshly `forte init`-ed vault shows users the knob without forcing a value.
- Unit tests in the style of `tests/test_config_service.py`: config with an `editor` value resolves it; config without one yields `editor=None`; a missing config file still yields `editor=None`.
Implementation Notes:
- This key is only *read* here; the precedence logic (`$VISUAL` → `$EDITOR` → this config value → hardcoded fallback) lives in the editor-session task, not in `config.py`. Keep `config.py` a plain reader.
- No env-var interpolation is needed for `editor` (unlike `api_keys.anthropic`) — it's a literal command name/path.

Task: Implement bulk-commit document format (serialize + parse)
ACs:
- A new pure module (e.g. `src/forte/services/agent/_bulk_format.py`) provides two functions with **no** Click / Rich / filesystem / DB imports:
  - `render(changes: list[ProposedChange]) -> str` — produces the editor file: an instructional header comment block, then three sections (`## New entities`, `## Links to existing entities`, `## Field updates`), with one line per proposal, each pre-filled with `[y]` and carrying a **stable, opaque change-id token** the parser keys on (e.g. `[y] c3  New person: Alice`). Empty sections are omitted or shown with a "(none)" placeholder — pick one and document it.
  - `parse(edited: str, changes: list[ProposedChange]) -> list[Decision]` — maps the edited text back to one `Decision` per original change, matched by change-id token, **independent of line order**. Rules: `[y]` → approved; `[n]` → rejected; a **missing** change id (line deleted) → rejected; an **unrecognized/blank** action token → rejected; comment/section/header lines are ignored.
- Line rendering is legible and mirrors `InteractiveReviewer._render` content: new entities show schema + name (+ aliases/fields if present); links show `candidate -> #<entity_id> (<entity_name>)`; field updates show the field key=value pairs and the target entity's display name. Include the supporting quote where the current TUI does.
- Unit tests cover: round-trip with no edits = all approved; flipping specific tokens to `[n]`; deleting a line = rejected; garbage action = rejected; reordering lines preserves correct mapping; a change list containing all three proposal kinds renders into the right sections.
Implementation Notes:
- The change-id token must be assigned by `render` deterministically from position in the `changes` list (e.g. `c0`, `c1`, …) and consumed by `parse` against the **same** `changes` list — `parse` takes the original list as its second argument so it never has to reconstruct proposals from text. This keeps the human-facing text free to be edited/garbled without breaking the mapping.
- The existing-entity id shown on link lines (the `#2` in the feature sketch) is **display context only** — do not use it as the parse key; use the opaque change-id token so links and new entities share one robust scheme.
- Keep the header text close to the sketch in `docs/input/2026-07-25 commit-feature-description.md` but describe the `[y]`/`[n]` scheme (not `[n]/[s]/[l]`), and state that deleted/invalid lines are skipped and that new records cannot be added here.

Task: Implement the editor-session boundary and terminal launcher
ACs:
- A small **boundary** is added to the agent package mirroring the `Reviewer` seam in `_review.py`: an `EditorSession` protocol (e.g. `src/forte/services/agent/_editor.py`) with a single method `edit(text: str) -> str` that takes the file contents to present and returns the edited contents. The agent package exports it (and any error type) from `src/forte/services/agent/__init__.py`, matching how `Reviewer`/`AutoApproveReviewer` are exported.
- A concrete **terminal** implementation lives in the driver layer (e.g. `src/forte/cli/bulk_editor.py`, mirroring `cli/review_tui.py`): it resolves the editor command via precedence `$VISUAL` → `$EDITOR` → `Config.editor` → hardcoded fallback chain (`vi`, then `nano`), writes `text` to a temp file, launches the editor as a subprocess against that file, waits, reads the edited contents back, and cleans up the temp file.
- If the editor process exits **non-zero**, the launcher raises a typed `EditorAbortedError` (exported alongside the boundary) so callers can abort the run and commit nothing. A clean (zero-exit) close returns the file contents as-is, even if unchanged.
- The launcher is injected, not hardwired, exactly like the LLM client: add a construction seam in `src/forte/cli/__init__.py` (mirroring `_build_llm_client`) that production wires to the terminal launcher and tests monkeypatch to a stub `EditorSession` whose `edit` is a scripted `str -> str` function. **No test ever spawns a real editor.**
- Tests cover: precedence resolution (env vars vs config vs fallback, using monkeypatched environment/config), round-trip through a fake editor that rewrites the file, and non-zero exit raising `EditorAbortedError`.
Implementation Notes:
- Keep the orchestrator (next task) free of Click/subprocess/tempfile — it depends only on the `EditorSession` protocol, just as it depends on `LLMClient` and `Reviewer` today. This preserves the "pipeline has no Click/Rich imports" invariant called out in `_review.py`/`_orchestrator.py`.
- Use `subprocess.run([*editor_argv, tmp_path])` with the editor string split via `shlex.split` so values like `"code --wait"` work; document that GUI editors need their wait flag.
- Use `tempfile` with a `.md`-ish suffix so editors apply reasonable syntax highlighting; ensure cleanup happens even on the abort path (`try/finally`).

Task: Implement the bulk orchestration flow
ACs:
- A new orchestration entry point (e.g. `process_document_bulk` in `src/forte/services/agent/_orchestrator.py`, or a `bulk: bool` branch — prefer a clearly separate function for readability) runs the flow:
  1. extract candidates and resolve each to a `ProposedLink` / `ProposedNewEntity` (reuse the existing steps unchanged);
  2. **eagerly** run field-extraction for **every** proposed entity (both new and linked), not just approved ones, producing `ProposedFieldSet`s;
  3. assemble the full `list[ProposedChange]`, `render` it (bulk-format task), pass through the injected `EditorSession.edit`, and `parse` the result into decisions;
  4. build the approved change set and `commit_changes`, honoring `dry_run` (skip commit, return a `ProcessResult` with `commit_report=None`) exactly as `process_document` does.
- **Edge-case handling**: when an approved `ProposedFieldSet` targets a new entity whose `ProposedNewEntity` was rejected, the new entity is **promoted back into** the approved set so it gets created, keeping `new_entity_ref` alignment intact for `commit_changes` (new entities first, in order). Covered by a dedicated test.
- If `EditorSession.edit` raises `EditorAbortedError`, the function lets it propagate (nothing has been committed at that point — commit is the last step) so the CLI can surface it.
- Returns the same `ProcessResult` shape the CLI already renders (`doc_id`, `approved_changes`, `commit_report`, `usage`, `dry_run`), so `_render_process_result` needs no changes.
- Integration tests (temp vault, real SQLite/markdown, stubbed LLM + stubbed editor) cover the spec scenarios: mixed approve/skip, deleted-line = skip, the promote-entity edge case, dry-run writes nothing, and the usage total accumulates across the (now larger) set of LLM calls.
Implementation Notes:
- Reuse `extract_entities`, `resolve_candidate`, `extract_fields`, and `commit_changes` as-is — this task is orchestration only, no new LLM steps.
- The `new_entity_ref` on a `FieldSetTarget` is an index into the approved-new-entities list in commit order (see the `_orchestrator.py` / `_commit.py` module docstrings). Because bulk mode may promote a rejected new entity back in (edge case), assign `new_entity_ref` values / order the final `approved_new` list **after** resolving promotions, so indices still line up with `commit_changes`' resolution scheme. Add a test asserting the promoted entity + its field-set commit correctly.
- Document at the top of the function the intentional divergence from option B: bulk mode field-extracts all proposals up front (more LLM calls) because everything is reviewed in one pass. Keep `usage` accumulation across every call so the cost summary stays accurate.

Task: Wire `--bulk-commit` into `agent ingest` and `agent process`
ACs:
- Both `agent process` and `agent ingest` gain a `--bulk-commit` flag (`is_flag=True`) alongside the existing `--yes` / `--dry-run`.
- Routing in the shared `_run_agent_process` helper:
  - `--yes` present → existing auto-approve path (`AutoApproveReviewer`, `process_document`); **`--bulk-commit` is ignored and no editor opens** (document precedence in `--help` text).
  - `--bulk-commit` without `--yes` → the bulk flow (previous task), passing the injected `EditorSession` from the new construction seam; `--dry-run` composes (editor opens, commit skipped).
  - neither → today's interactive one-at-a-time flow, unchanged.
- Result rendering reuses `_render_process_result` unchanged. On `EditorAbortedError`, the command raises `click.ClickException` with a clear message and exits non-zero, having committed nothing.
- When there are zero proposals in bulk mode, the editor is not opened and the existing "Nothing to do" summary is printed.
- Integration tests via `CliRunner` + monkeypatched LLM and editor seams cover: `--bulk-commit` happy path, `--bulk-commit --yes` (no editor invoked — assert the editor stub was never called), `--bulk-commit --dry-run` (writes nothing), editor-abort → non-zero exit, and `agent ingest <path> --bulk-commit` end-to-end.
Implementation Notes:
- Follow the existing command pattern in `src/forte/cli/__init__.py`: thin command, vault discovery, config load, map typed errors to `click.ClickException`. Add the editor-session construction seam next to `_build_llm_client` so tests can monkeypatch it (the editor task owns creating that seam; this task consumes it).
- Keep the precedence rule (`--yes` beats `--bulk-commit`) in one place — the `_run_agent_process` helper — so both commands behave identically. Reflect it in each flag's `help` string.
- No change to `doc ingest` (the non-agent mechanical ingest) — this flag lives only under the `agent` group where a review flow exists.

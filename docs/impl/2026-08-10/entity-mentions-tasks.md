# docs/impl/2026-08-10/entity-mentions-tasks.md

Feature: show **mentions** in `forte entity show` — the documents that mention an entity —
mirroring the `Mentions:` section that `forte doc show` already prints for the opposite
direction. This closes the "Linked docs / mentions in `entity show`" gap that
[docs/spec/forte-entity.md](../../spec/forte-entity.md) currently lists as out of scope, and
un-xfails `tests/e2e/test_doc_links.py::test_linking_is_reflected_on_the_entity`.

The `mentions` table and its `doc link` / `doc unlink` writers already exist; nothing new is
stored. All that is missing is the reverse query (mentions **by entity**) and the display.

- Add a reverse mention query to `IMentionDb` / `SqliteMentionDb`
- Add `EntityService.list_mentioning_documents`, wired in `main.py`
- Print a `Mentions:` section in `forte entity show`
- Update the entity spec and e2e tests

---

Task: Add a reverse mention query to `IMentionDb` / `SqliteMentionDb`
ACs:
- `interface/mention_db.py` declares `list_for_entity(self, entity_id: int) -> list[Mention]`, documented as returning every mention row belonging to an entity, ordered by doc id.
- `client/sqlite_mention_db.py` implements it against the `mentions` table, following the existing per-call `VaultLayout` + `sqlite3.connect` + `finally: conn.close()` shape used by `list_for_doc`.
- Existing `IMentionDb` methods and behavior are unchanged.
Implementation Notes:
- This is the mirror of the existing `list_for_doc`: same SELECT column list and same `Mention(...)` row mapping, with `WHERE entity_id = ? ORDER BY doc_id`.
- Per the style guide's interface method ordering (existence check, then CRUD create/read/list/delete, then extra queries), put `list_for_entity` directly after `list_for_doc` in both the interface and the client, so the two list methods read as a pair.
- The `mentions` table is created by the `forte init` bootstrap — no migration or schema change is needed here. Check whether an index on `entity_id` exists; if lookups are only by `doc_id` today, note it but do NOT add a migration in this task (vault DBs in the wild would need one) — MVP vaults are small enough that a table scan is fine.

Task: Add `EntityService.list_mentioning_documents`, wired in `main.py`
ACs:
- `EntityService` gains `list_mentioning_documents(self, id: int) -> list[Document]`, returning the documents that mention the entity, ordered by doc id.
- It raises `EntityNotFoundError` if no entity with that id exists (documented in the docstring's `Raises:` section), consistent with `get_entity`.
- A mention row pointing at a document that no longer exists is **skipped**, not raised on — a stale row can never make `entity show` fail.
- `EntityService.__init__` takes the new dependencies it needs (`IMentionDb`, `IDocumentDb`) as constructor-injected interfaces, and `src/forte/main.py` is updated to pass them. `mention_db` is already constructed in `main.py` (line ~67) — but *after* `entity_service`; reorder the wiring so the dependencies exist first.
- No existing `EntityService` behavior changes.
Implementation Notes:
- Mirror `DocumentService.list_linked_entities` (src/forte/service/document_service.py:214) almost exactly — same not-found check first, same skip-missing-on-the-other-side loop, same final `sorted(..., key=lambda d: d.id or 0)`. Keeping the two symmetric is the point.
- Placement decision: the query lives on `EntityService` rather than `DocumentService` because `CliEntityController` only holds an `EntityService`, and controllers should call one service per feature. The cost is that `EntityService` now depends on `IDocumentDb`; that's acceptable — mentions are inherently a two-sided relation, and `DocumentService` already reaches across into `IEntityDb` for the same reason.
- Note the asymmetry worth knowing about: `DocumentService.remove_document` cleans up mentions via `remove_for_doc`, but `EntityService.remove_entity` has no equivalent `remove_for_entity`, so removing an entity leaves orphan mention rows behind. Those orphans are already tolerated by `doc show`'s skip-missing logic and will be by this one too. Do NOT fix that here — it's a separate cleanup task; just don't let it break this display.
- Import `Document` from `model/document.py` for the return type.

Task: Print a `Mentions:` section in `forte entity show`
ACs:
- `forte entity show <id>` prints, after the entity's fields, a `Mentions:` section listing each document that mentions the entity, one per line.
- Formatting mirrors `doc show`'s section exactly, with the sides swapped: a blank line, then either `Mentions:` followed by indented `  doc #<id> <name>` lines, or the single line `Mentions: (none)` when there are none.
- The service call is wrapped in the controller's existing `try/except (EntityError, VaultError)` → `click.ClickException` pattern; `entity show` for a nonexistent id still fails the same way it does today.
- `--vault` continues to work unchanged for `entity show`.
Implementation Notes:
- The code to copy is `CliDocumentController._show` (src/forte/controller/cli_document_controller.py) — the `if linked: ... else: click.echo("Mentions: (none)")` block at the end. Keep the string `Mentions:` byte-identical so the two outputs read as one feature.
- All logic stays in `CliEntityController._show`; the nested Click callback keeps just unpacking args, per the style guide.
- Fetch the entity and the mentioning docs inside the same `try`, so a vault error surfaces once.

Task: Update the entity spec and e2e tests
ACs:
- `docs/spec/forte-entity.md` no longer lists "Linked docs / mentions in `entity show`" under **Out of scope**, and instead carries Gherkin scenarios for: an entity with no mentions (`Mentions: (none)`), an entity mentioned by one doc, an entity mentioned by multiple docs (listed in doc-id order), and a mention surviving/disappearing across `doc link` → `doc unlink`.
- `tests/e2e/test_doc_links.py::test_linking_is_reflected_on_the_entity` has its `@pytest.mark.xfail(strict=True, ...)` removed and passes, and the module docstring's note about the reverse direction being unimplemented is deleted.
- `tests/e2e/test_entity_crud.py` (or `test_doc_links.py`, whichever reads more naturally — mentions are a link concern, so prefer the latter) covers the multi-doc and unlink cases end to end.
- The full e2e suite passes: `uv run pytest`.
Implementation Notes:
- The xfail is `strict=True`, so it will start FAILING as an unexpected pass the moment the display lands — that's the intended tripwire. Removing it is part of this feature, not an afterthought.
- That test already asserts on `"kickoff-notes.md"` (the doc name defaults to the source filename), which matches the `doc #<id> <name>` line format. Confirm rather than assume.
- Per the e2e conventions in `docs/style-guide.md`: `tmp_path` + a fake `HOME`, Gherkin comments per block, and assertions only on what a user can see (stdout / exit code) — never on `mentions` table rows from an entity-side test.
- This project has no unit-test suite anymore (`tests/` holds e2e only), so these e2e tests are the whole safety net for the three tasks above — cover the empty case as deliberately as the populated one.

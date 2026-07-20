# docs/impl/2026-07-20/doc-remove-tasks.md

- Add `remove` to `DocumentRepository` (db layer)
- Add `remove_document` to the document service layer, with mention cleanup
- Add `forte doc remove <id>` CLI command
- Add spec scenarios for `forte doc remove` to docs/spec/forte-doc.md
- Add integration tests for `forte doc remove`

Task: Add `remove` to `DocumentRepository` (db layer)
ACs:
- `DocumentRepository.remove(doc_id: int) -> None` deletes the `documents` row for `doc_id`.
- It also deletes the on-disk raw copy (`raw_path`) and processed copy (`processed_path`) if they exist, mirroring `EntityRepository.remove`'s "delete markdown file(s) + row together" pattern.
- If either file is already missing on disk, the method does not raise — same defensive `path.exists()` check used in `EntityRepository.remove`.
- No existence check for `doc_id` is required here; that's the service layer's job (matches the existing `EntityRepository.remove` contract, where the repo trusts the caller).
Implementation Notes:
- Model this directly on `EntityRepository.remove` (src/forte/db/entity_repository.py:212-227): `SELECT` the row first to get `raw_path`/`processed_path`, then in one `with conn:` transaction `DELETE FROM documents WHERE id = ?`, then unlink both files if present.
- Paths in the DB are vault-relative (see `DocumentRepository._rel_path`); resolve them the same way `_abs_path` does for entities before calling `.unlink()`.
- This method does NOT touch the `mentions` table — that's out of scope for the db layer and handled by the service layer task below.

Task: Add `remove_document` to the document service layer, with mention cleanup
ACs:
- `remove_document(root: Path, id: int) -> None` in `src/forte/services/document.py` raises `DocumentNotFoundError` if no document with `id` exists (same pattern as `remove_entity`).
- Before deleting the document, it removes all `mentions` rows referencing that `doc_id`, so no dangling mentions point at a deleted document.
- Then calls `DocumentRepository(root).remove(id)` to delete the DB row + raw/processed files.
Implementation Notes:
- Mirror `remove_entity` (src/forte/services/entity.py:178-183) for the not-found check and overall shape.
- `MentionRepository` has no "remove all for doc" method today — only `remove(doc_id, entity_id)` for a single pair (src/forte/db/mention_repository.py:41-49). Add a `remove_for_doc(doc_id: int) -> None` method there (`DELETE FROM mentions WHERE doc_id = ?`), and call it from `remove_document` before deleting the document row.
- Entities themselves are NOT deleted or modified — only the mention links are cleaned up. This matches the spec's framing that mentions are "pure DB rows" separate from entity lifecycle.

Task: Add `forte doc remove <id>` CLI command
ACs:
- `forte doc remove <id>` deletes the document and prints a confirmation message including the id (and name, if convenient) of the removed document.
- Exits 0 on success.
- If `id` does not exist, prints an error message and exits non-zero (catch `DocumentNotFoundError`, same pattern as other doc/entity commands).
- Supports a `--yes`/`-y` flag to skip an interactive confirmation prompt before deleting, matching the existing `--yes`/`-y` flags on `doc ingest`, `entity add`, and `entity remove` (src/forte/cli/__init__.py:276-277 shows the entity remove pattern to copy).
Implementation Notes:
- Add as `@doc.command("remove")` in src/forte/cli/__init__.py, alongside the other `doc_*` commands (after `doc_unlink`, around line 411).
- Fetch the document first (via `get_document`) to show its name in the confirmation prompt and success message, same as `entity remove`'s confirmation flow.
- Call the new `remove_document` service function; catch `DocumentNotFoundError` and map to a Click error / non-zero exit, consistent with how other commands map service exceptions.

Task: Add spec scenarios for `forte doc remove` to docs/spec/forte-doc.md
ACs:
- docs/spec/forte-doc.md's intro line is updated to include `doc remove` in the list of commands the file covers.
- New Gherkin scenarios are added covering: removing an existing document (raw + processed files deleted, DB row gone, associated mentions gone, `doc list`/`doc show` no longer show it), removing a non-existent id (error, non-zero exit, nothing changed), and the `--yes` flag skipping the confirmation prompt.
Implementation Notes:
- Follow the existing scenario style/format already in the file (Given/When/Then blocks per scenario, one behavior per scenario).
- Call out explicitly that removing a document does not remove the entities it was linked to, only the mention rows — this is a easy point of confusion given `doc unlink` already exists for removing individual links.

Task: Add integration tests for `forte doc remove`
ACs:
- New tests in tests/test_doc_cli.py (CLI-level, following the integration-first testing approach in solution-design.md) cover: successful removal (files gone from disk, `documents` row gone, `doc list`/`doc show` reflect the removal), removing a doc that had mentions (mentions are cleaned up, linked entities are untouched), removing a non-existent id (error + non-zero exit), and `--yes` bypassing the prompt.
- If repo/service-level tests exist for the analogous entity-remove flow (check tests/test_document_repository.py and tests/test_document_service.py for structure), add matching unit-level tests for `DocumentRepository.remove` and `remove_document` there too.
Implementation Notes:
- Follow this project's existing test file conventions — real markdown files + real SQLite against a temp vault, no mocking of the DB/filesystem (per "Testing" section of solution-design.md).
- Check for an existing entity-remove test as a template for the CLI confirmation-prompt test pattern (simulating `y`/`n` input vs. passing `--yes`).

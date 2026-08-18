"""End-to-end tests for `forte doc create`: creating a document by
typing/pasting text into the user's editor, rather than ingesting an
existing file.

Doc ingest/list/show/remove is covered in `test_doc_crud.py`. Doc-to-entity
linking is covered in `test_doc_links.py`; this file only checks that a
created doc can participate in it.
"""

import os
import shlex
import subprocess
import sys
from pathlib import Path

# Resolve the CLI from the same virtualenv running pytest, so the test does
# not depend on `forte` being on the ambient PATH.
FORTE_BIN = Path(sys.executable).parent / "forte"

PASTED_TEXT = "# Standup Notes\n\nPasted straight from my editor.\n"


def forte(args, home, env=None):
    """Invoke the forte CLI with `home` as HOME, so the vault registry is
    written to a temp dir rather than the real one.

    `args` is the command line as a single string, split shell-style — so
    quoted arguments (`--name "Kickoff Notes"`) survive as one argument.
    `env` optionally overrides/extends the subprocess environment (e.g. to
    point `EDITOR` at a fake editor script)."""
    return subprocess.run(
        [str(FORTE_BIN), *shlex.split(args)],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(home), **(env or {})},
    )


def a_vault(tmp_path):
    """Set up a home with one registered vault, which becomes the default."""
    home = tmp_path / "home"
    vault_dir = tmp_path / "vault"
    home.mkdir()
    vault_dir.mkdir()

    assert forte(f"vault create testvault {vault_dir}", home).returncode == 0
    return home, vault_dir


def a_fake_editor(tmp_path, name, body):
    """Write a tiny fake-editor script into tmp_path and return an EDITOR
    env value that invokes it with the running interpreter, so it doesn't
    depend on an ambient `python` on PATH.

    `body` is the Python source for the script; it receives the temp file
    forte hands the editor as sys.argv[1]."""
    script = tmp_path / name
    script.write_text(body)
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"


def an_editor_that_writes(tmp_path, text):
    """An EDITOR that overwrites the buffer it's handed with fixed text."""
    return a_fake_editor(
        tmp_path,
        "fake_editor_write.py",
        "import sys\n"
        f"with open(sys.argv[1], 'w') as f:\n"
        f"    f.write({text!r})\n",
    )


def an_editor_that_fails(tmp_path):
    """An EDITOR that exits non-zero without touching the buffer."""
    return a_fake_editor(
        tmp_path,
        "fake_editor_fail.py",
        "import sys\nsys.exit(1)\n",
    )


def an_editor_that_writes_nothing(tmp_path):
    """An EDITOR that exits 0 but leaves the buffer empty (e.g. the user
    saved without typing anything)."""
    return a_fake_editor(
        tmp_path,
        "fake_editor_empty.py",
        "import sys\n",
    )


# Scenario: create a document from pasted editor content
def test_create_a_document_from_pasted_editor_content(tmp_path):
    # Given: a vault, and an editor that writes fixed content into the buffer
    home, _ = a_vault(tmp_path)
    editor = an_editor_that_writes(tmp_path, PASTED_TEXT)

    # When: the user runs `forte doc create <name>`
    result = forte('doc create "Standup Notes"', home, env={"EDITOR": editor})

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: the output reports the new doc's id and name
    assert "Created doc #1: Standup Notes" in result.stdout


# Scenario: a created document appears in list and show
def test_a_created_document_appears_in_list_and_show(tmp_path):
    # Given: a vault, and an editor that writes fixed content into the buffer
    home, _ = a_vault(tmp_path)
    editor = an_editor_that_writes(tmp_path, PASTED_TEXT)

    # When: the user runs `forte doc create <name>`
    assert (
        forte('doc create "Standup Notes"', home, env={"EDITOR": editor}).returncode
        == 0
    )

    # Then: the doc appears in `forte doc list`
    assert "#1  Standup Notes" in forte("doc list", home).stdout

    # Then: `forte doc show <id>` returns the pasted content
    shown = forte("doc show 1", home)
    assert shown.returncode == 0, shown.stderr
    assert "# Standup Notes" in shown.stdout
    assert "Pasted straight from my editor." in shown.stdout


# Scenario: a created document is stored as raw and processed copies
def test_a_created_document_is_stored_as_raw_and_processed_copies(tmp_path):
    # Given: a vault, and an editor that writes fixed content into the buffer
    home, vault_dir = a_vault(tmp_path)
    editor = an_editor_that_writes(tmp_path, PASTED_TEXT)

    # When: the user runs `forte doc create <name>`
    result = forte('doc create "Standup Notes"', home, env={"EDITOR": editor})
    assert result.returncode == 0, result.stderr

    # Then: a raw copy exists under `docs/raw/`, containing the pasted text
    raw_files = list((vault_dir / "docs" / "raw").glob("*.md"))
    assert len(raw_files) == 1
    assert raw_files[0].read_text() == PASTED_TEXT

    # Then: a processed copy exists under `docs/processed/`, with frontmatter
    processed = vault_dir / "docs" / "processed" / "1.md"
    assert processed.is_file()
    processed_text = processed.read_text()
    assert processed_text.startswith("---\n")
    assert "name: Standup Notes" in processed_text
    assert "content_hash:" in processed_text

    # Then: the processed copy's body carries the pasted text verbatim
    assert PASTED_TEXT.strip() in processed_text


# Scenario: a created document can be linked to an entity
def test_a_created_document_can_be_linked_to_an_entity(tmp_path):
    # Given: a vault with a schema, an entity, and a created doc
    home, _ = a_vault(tmp_path)
    editor = an_editor_that_writes(tmp_path, PASTED_TEXT)
    assert forte("schema add meeting --field date", home).returncode == 0
    assert forte('entity add meeting --name "Kickoff"', home).returncode == 0
    assert (
        forte('doc create "Standup Notes"', home, env={"EDITOR": editor}).returncode
        == 0
    )

    # When: the user runs `forte doc link <doc_id> <entity_id>`
    result = forte("doc link 1 1", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr
    assert "Linked doc #1 to entity #1" in result.stdout

    # Then: `forte doc show <doc_id>` lists the entity under Mentions
    shown = forte("doc show 1", home)
    assert "entity #1 [meeting] Kickoff" in shown.stdout
    assert "Mentions: (none)" not in shown.stdout


# Scenario: an editor that exits non-zero creates no document
def test_an_editor_that_exits_nonzero_creates_no_document(tmp_path):
    # Given: a vault, and an editor that exits non-zero
    home, vault_dir = a_vault(tmp_path)
    editor = an_editor_that_fails(tmp_path)

    # When: the user runs `forte doc create <name>`
    result = forte('doc create "Standup Notes"', home, env={"EDITOR": editor})

    # Then: we get an error
    assert result.returncode != 0

    # Then: no doc is registered — `forte doc list` is still empty
    assert "No documents yet." in forte("doc list", home).stdout

    # Then: no raw or processed copies were written to the vault
    assert list((vault_dir / "docs" / "raw").glob("*")) == []
    assert list((vault_dir / "docs" / "processed").glob("*")) == []


# Scenario: `forte doc create` offers the link step after saving
def test_doc_create_offers_the_link_step_after_saving(tmp_path, pty_forte):
    # Given: a vault with a person entity, and an editor that writes fixed
    # content into the buffer
    home, _ = a_vault(tmp_path)
    editor = an_editor_that_writes(tmp_path, PASTED_TEXT)
    assert forte("schema add person", home).returncode == 0
    assert forte('entity add person --name "Alice"', home).returncode == 0

    # When: the user runs `forte doc create <name>` and saves in the editor
    session = pty_forte('doc create "Standup Notes"', home, env={"EDITOR": editor})

    # Then: the document is stored and assigned an id before any link
    # prompt is shown
    session.wait_for("Created doc #1: Standup Notes")

    # Then: the same interactive link prompt as `link-interactive` runs
    session.wait_for("Link entities (type to search, Enter to add, empty line to finish):")

    # When: the user types `ali` and selects `#1 [person] Alice`
    session.type_text("ali")
    session.wait_for("#1 [person] Alice")
    session.tab()
    session.enter()
    session.wait_for("Linked: #1 [person] Alice")

    # When: the user finishes the session with an empty line
    session.enter()
    returncode = session.wait_exit()

    # Then: the process reports the entities linked, and exits 0
    assert returncode == 0
    assert "Linked 1 entity to doc #1: Standup Notes" in session.output

    # Then: `forte doc show 1` lists the entity under Mentions
    shown = forte("doc show 1", home)
    assert "entity #1 [person] Alice" in shown.stdout


# Scenario: `forte doc create --no-link` skips the link step
def test_doc_create_no_link_skips_the_link_step(tmp_path):
    # Given: a vault, and an editor that writes fixed content into the buffer
    home, _ = a_vault(tmp_path)
    editor = an_editor_that_writes(tmp_path, PASTED_TEXT)

    # When: the user runs `forte doc create <name> --no-link`
    result = forte('doc create "Standup Notes" --no-link', home, env={"EDITOR": editor})

    # Then: the document is stored as usual, and the process exits 0
    assert result.returncode == 0, result.stderr
    assert "Created doc #1: Standup Notes" in result.stdout

    # Then: the interactive link prompt did not run
    assert "Link entities" not in result.stdout

    # Then: no row was added to the mentions table for the new document
    shown = forte("doc show 1", home)
    assert "Mentions: (none)" in shown.stdout


# Scenario: an editor that saves an empty buffer creates no document
def test_an_editor_that_saves_an_empty_buffer_creates_no_document(tmp_path):
    # Given: a vault, and an editor that saves without writing any content
    home, vault_dir = a_vault(tmp_path)
    editor = an_editor_that_writes_nothing(tmp_path)

    # When: the user runs `forte doc create <name>`
    result = forte('doc create "Standup Notes"', home, env={"EDITOR": editor})

    # Then: we get an error
    assert result.returncode != 0

    # Then: no doc is registered — `forte doc list` is still empty
    assert "No documents yet." in forte("doc list", home).stdout

    # Then: no raw or processed copies were written to the vault
    assert list((vault_dir / "docs" / "raw").glob("*")) == []
    assert list((vault_dir / "docs" / "processed").glob("*")) == []

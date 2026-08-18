"""End-to-end tests for the `forte doc` command group: ingest/list/show/remove.

Doc-to-entity linking lives in `test_doc_links.py`.
"""

import os
import shlex
import subprocess
import sys
from pathlib import Path

# Resolve the CLI from the same virtualenv running pytest, so the test does
# not depend on `forte` being on the ambient PATH.
FORTE_BIN = Path(sys.executable).parent / "forte"

SOURCE_TEXT = "# Kickoff\n\nWe met today.\n"


def forte(args, home):
    """Invoke the forte CLI with `home` as HOME, so the vault registry is
    written to a temp dir rather than the real one.

    `args` is the command line as a single string, split shell-style — so
    quoted arguments (`--name "Kickoff Notes"`) survive as one argument."""
    return subprocess.run(
        [str(FORTE_BIN), *shlex.split(args)],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(home)},
    )


def a_vault(tmp_path):
    """Set up a home with one registered vault, which becomes the default."""
    home = tmp_path / "home"
    vault_dir = tmp_path / "vault"
    home.mkdir()
    vault_dir.mkdir()

    assert forte(f"vault create testvault {vault_dir}", home).returncode == 0
    return home, vault_dir


def a_source_file(tmp_path, name="notes.md", content=SOURCE_TEXT):
    """Write a source document somewhere outside the vault, as a user would
    have it sitting on their own disk before ingesting."""
    source_dir = tmp_path / "source"
    source_dir.mkdir(exist_ok=True)
    path = source_dir / name
    path.write_text(content)
    return path


# Scenario: ingest a document
def test_ingest_a_document(tmp_path):
    # Given: a vault, and a markdown file on disk outside the vault
    home, _ = a_vault(tmp_path)
    source = a_source_file(tmp_path)

    # When: the user runs `forte doc ingest <path>`
    result = forte(f"doc ingest {source}", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: the output reports the new doc's id and name
    assert "Ingested doc #1: notes.md" in result.stdout

    # Then: the doc appears in `forte doc list`
    assert "#1  notes.md" in forte("doc list", home).stdout


# Scenario: ingesting a document copies it into the vault
def test_ingesting_a_document_copies_it_into_the_vault(tmp_path):
    # Given: a vault, and a markdown file on disk outside the vault
    home, vault_dir = a_vault(tmp_path)
    source = a_source_file(tmp_path)

    # When: the user runs `forte doc ingest <path>`
    result = forte(f"doc ingest {source}", home)
    assert result.returncode == 0, result.stderr

    # Then: a copy exists under `docs/raw/`, byte-for-byte identical to the source
    raw = vault_dir / "docs" / "raw" / "notes.md"
    assert raw.is_file()
    assert raw.read_bytes() == source.read_bytes()

    # Then: a copy exists under `docs/processed/`, with YAML frontmatter prepended
    processed = vault_dir / "docs" / "processed" / "1.md"
    assert processed.is_file()
    processed_text = processed.read_text()
    assert processed_text.startswith("---\n")
    assert f"source_path: {source}" in processed_text
    assert "content_hash:" in processed_text
    assert "ingested_at:" in processed_text

    # Then: the processed copy's body still contains the source text
    assert SOURCE_TEXT in processed_text

    # Then: the original file on the user's disk is untouched
    assert source.read_text() == SOURCE_TEXT


# Scenario: ingest a document with an explicit name
def test_ingest_a_document_with_an_explicit_name(tmp_path):
    # Given: a vault, and a markdown file on disk outside the vault
    home, _ = a_vault(tmp_path)
    source = a_source_file(tmp_path)

    # When: the user runs `forte doc ingest <path> --name "Kickoff Notes"`
    result = forte(f'doc ingest {source} --name "Kickoff Notes"', home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: `forte doc list` shows the doc under that name, not the filename
    listed = forte("doc list", home)
    assert "#1  Kickoff Notes" in listed.stdout
    assert "notes.md" not in listed.stdout


# Scenario: ingest a document that does not exist
def test_ingest_a_document_that_does_not_exist(tmp_path):
    # Given: a vault, and a path that points at no file
    home, _ = a_vault(tmp_path)
    missing = tmp_path / "source" / "missing.md"

    # When: the user runs `forte doc ingest <path>`
    result = forte(f"doc ingest {missing}", home)

    # Then: we get an error
    assert result.returncode != 0
    assert "Source file not found" in result.stderr

    # Then: no doc is registered — `forte doc list` is still empty
    assert "No documents yet." in forte("doc list", home).stdout


# Scenario: `forte doc ingest` offers the link step after storing the document
def test_doc_ingest_offers_the_link_step_after_storing_the_document(tmp_path, pty_forte):
    # Given: a vault with a person entity, and a file to ingest
    home, _ = a_vault(tmp_path)
    source = a_source_file(tmp_path)
    assert forte("schema add person", home).returncode == 0
    assert forte('entity add person --name "Alice"', home).returncode == 0

    # When: the user runs `forte doc ingest <path>`
    session = pty_forte(f"doc ingest {source}", home)

    # Then: the document is copied, extracted, and assigned an id before
    # any link prompt is shown
    session.wait_for("Ingested doc #1: notes.md")

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
    assert "Linked 1 entity to doc #1: notes.md" in session.output

    # Then: `forte doc show 1` lists the entity under Mentions
    shown = forte("doc show 1", home)
    assert "entity #1 [person] Alice" in shown.stdout


# Scenario: `forte doc ingest --no-link` skips the link step
def test_doc_ingest_no_link_skips_the_link_step(tmp_path):
    # Given: a vault, and a file to ingest
    home, _ = a_vault(tmp_path)
    source = a_source_file(tmp_path)

    # When: the user runs `forte doc ingest <path> --no-link`
    result = forte(f"doc ingest {source} --no-link", home)

    # Then: the document is stored as usual, and the process exits 0
    assert result.returncode == 0, result.stderr
    assert "Ingested doc #1: notes.md" in result.stdout

    # Then: the interactive link prompt did not run
    assert "Link entities" not in result.stdout

    # Then: no row was added to the mentions table for the new document
    shown = forte("doc show 1", home)
    assert "Mentions: (none)" in shown.stdout


# Scenario: list documents
def test_list_documents(tmp_path):
    # Given: a vault with two ingested docs
    home, _ = a_vault(tmp_path)
    first = a_source_file(tmp_path, "notes.md")
    second = a_source_file(tmp_path, "other.md", "Another doc.\n")
    assert forte(f"doc ingest {first}", home).returncode == 0
    assert forte(f"doc ingest {second}", home).returncode == 0

    # When: the user runs `forte doc list`
    result = forte("doc list", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: the output shows both docs, with their ids and names
    assert "#1  notes.md" in result.stdout
    assert "#2  other.md" in result.stdout


# Scenario: list documents in an empty vault
def test_list_documents_in_an_empty_vault(tmp_path):
    # Given: a vault with no ingested docs
    home, _ = a_vault(tmp_path)

    # When: the user runs `forte doc list`
    result = forte("doc list", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: the output says there are no documents yet
    assert "No documents yet." in result.stdout


# Scenario: show a document
def test_show_a_document(tmp_path):
    # Given: a vault with one ingested doc
    home, _ = a_vault(tmp_path)
    source = a_source_file(tmp_path)
    assert forte(f"doc ingest {source}", home).returncode == 0

    # When: the user runs `forte doc show <id>`
    result = forte("doc show 1", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: the output shows the doc's id, name, source path, ingest time, and status
    assert "#1 notes.md" in result.stdout
    assert f"Source: {source}" in result.stdout
    assert "Ingested: " in result.stdout
    assert "Status: ingested" in result.stdout

    # Then: the output shows the doc's text body
    assert "# Kickoff" in result.stdout
    assert "We met today." in result.stdout

    # Then: the output shows a Mentions section, empty for a doc with no links
    assert "Mentions: (none)" in result.stdout


# Scenario: show a document that does not exist
def test_show_a_document_that_does_not_exist(tmp_path):
    # Given: a vault with no ingested docs
    home, _ = a_vault(tmp_path)

    # When: the user runs `forte doc show 999`
    result = forte("doc show 999", home)

    # Then: we get an error
    assert result.returncode != 0
    assert "Document #999 does not exist." in result.stderr


# Scenario: remove a document
def test_remove_a_document(tmp_path):
    # Given: a vault with two ingested docs
    home, vault_dir = a_vault(tmp_path)
    first = a_source_file(tmp_path, "notes.md")
    second = a_source_file(tmp_path, "other.md", "Another doc.\n")
    assert forte(f"doc ingest {first}", home).returncode == 0
    assert forte(f"doc ingest {second}", home).returncode == 0

    # When: the user runs `forte doc remove <id> -y`
    result = forte("doc remove 1 -y", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr
    assert "Removed doc #1: notes.md" in result.stdout

    # Then: `forte doc list` no longer shows that doc
    listed = forte("doc list", home)
    assert "notes.md" not in listed.stdout

    # Then: `forte doc list` still shows the other doc
    assert "#2  other.md" in listed.stdout

    # Then: the doc's raw and processed copies are gone from the vault
    assert not (vault_dir / "docs" / "raw" / "notes.md").exists()
    assert not (vault_dir / "docs" / "processed" / "1.md").exists()

    # Then: the other doc's copies are still on disk
    assert (vault_dir / "docs" / "raw" / "other.md").is_file()
    assert (vault_dir / "docs" / "processed" / "2.md").is_file()

    # Then: the original file on the user's disk is untouched
    assert first.read_text() == SOURCE_TEXT


# Scenario: remove a document that does not exist
def test_remove_a_document_that_does_not_exist(tmp_path):
    # Given: a vault with no ingested docs
    home, _ = a_vault(tmp_path)

    # When: the user runs `forte doc remove 999 -y`
    result = forte("doc remove 999 -y", home)

    # Then: we get an error
    assert result.returncode != 0
    assert "Document #999 does not exist." in result.stderr

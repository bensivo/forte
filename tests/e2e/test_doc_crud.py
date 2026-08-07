"""End-to-end tests for the `forte doc` command group: ingest/list/show/remove.

Doc-to-entity linking lives in `test_doc_links.py`.
"""

import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

# Resolve the CLI from the same virtualenv running pytest, so the test does
# not depend on `forte` being on the ambient PATH.
FORTE_BIN = Path(sys.executable).parent / "forte"


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


def a_source_file(tmp_path, name="notes.md", content="# Kickoff\n\nWe met today.\n"):
    """Write a source document somewhere outside the vault, as a user would
    have it sitting on their own disk before ingesting."""
    source_dir = tmp_path / "source"
    source_dir.mkdir(exist_ok=True)
    path = source_dir / name
    path.write_text(content)
    return path


# Scenario: ingest a document
@pytest.mark.skip(reason="TODO: implement")
def test_ingest_a_document(tmp_path):
    # Given: a vault, and a markdown file on disk outside the vault
    # When: the user runs `forte doc ingest <path>`
    # Then: the process exits with status code 0
    # Then: the output reports the new doc's id and name
    # Then: the doc appears in `forte doc list`
    ...


# Scenario: ingesting a document copies it into the vault
@pytest.mark.skip(reason="TODO: implement")
def test_ingesting_a_document_copies_it_into_the_vault(tmp_path):
    # Given: a vault, and a markdown file on disk outside the vault
    # When: the user runs `forte doc ingest <path>`
    # Then: a copy exists under `docs/raw/`, byte-for-byte identical to the source
    # Then: a copy exists under `docs/processed/`, with YAML frontmatter prepended
    # Then: the processed copy's body still contains the source text
    # Then: the original file on the user's disk is untouched
    ...


# Scenario: ingest a document with an explicit name
@pytest.mark.skip(reason="TODO: implement")
def test_ingest_a_document_with_an_explicit_name(tmp_path):
    # Given: a vault, and a markdown file on disk outside the vault
    # When: the user runs `forte doc ingest <path> --name "Kickoff Notes"`
    # Then: the process exits with status code 0
    # Then: `forte doc list` shows the doc under that name, not the filename
    ...


# Scenario: ingest a document that does not exist
@pytest.mark.skip(reason="TODO: implement")
def test_ingest_a_document_that_does_not_exist(tmp_path):
    # Given: a vault, and a path that points at no file
    # When: the user runs `forte doc ingest <path>`
    # Then: we get an error
    # Then: no doc is registered — `forte doc list` is still empty
    ...


# Scenario: list documents
@pytest.mark.skip(reason="TODO: implement")
def test_list_documents(tmp_path):
    # Given: a vault with two ingested docs
    # When: the user runs `forte doc list`
    # Then: the process exits with status code 0
    # Then: the output shows both docs, with their ids and names
    ...


# Scenario: list documents in an empty vault
@pytest.mark.skip(reason="TODO: implement")
def test_list_documents_in_an_empty_vault(tmp_path):
    # Given: a vault with no ingested docs
    # When: the user runs `forte doc list`
    # Then: the process exits with status code 0
    # Then: the output says there are no documents yet
    ...


# Scenario: show a document
@pytest.mark.skip(reason="TODO: implement")
def test_show_a_document(tmp_path):
    # Given: a vault with one ingested doc
    # When: the user runs `forte doc show <id>`
    # Then: the process exits with status code 0
    # Then: the output shows the doc's id, name, source path, ingest time, and status
    # Then: the output shows the doc's text body
    # Then: the output shows a Mentions section, empty for a doc with no links
    ...


# Scenario: show a document that does not exist
@pytest.mark.skip(reason="TODO: implement")
def test_show_a_document_that_does_not_exist(tmp_path):
    # Given: a vault with no ingested docs
    # When: the user runs `forte doc show 999`
    # Then: we get an error
    ...


# Scenario: remove a document
@pytest.mark.skip(reason="TODO: implement")
def test_remove_a_document(tmp_path):
    # Given: a vault with two ingested docs
    # When: the user runs `forte doc remove <id> -y`
    # Then: the process exits with status code 0
    # Then: `forte doc list` no longer shows that doc
    # Then: `forte doc list` still shows the other doc
    # Then: the doc's raw and processed copies are gone from the vault
    # Then: the other doc's copies are still on disk
    # Then: the original file on the user's disk is untouched
    ...


# Scenario: remove a document that does not exist
@pytest.mark.skip(reason="TODO: implement")
def test_remove_a_document_that_does_not_exist(tmp_path):
    # Given: a vault with no ingested docs
    # When: the user runs `forte doc remove 999 -y`
    # Then: we get an error
    ...

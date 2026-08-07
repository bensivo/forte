"""End-to-end tests for linking documents to entities: `forte doc link` and
`forte doc unlink`.

Skeletons only — bodies are Gherkin comments describing the scenario. Fill
them in one at a time, following the style of `test_vault_crud.py`.

Note: the reverse direction — `forte entity show` listing the docs that link
to it — is not implemented yet. Those scenarios are marked below.
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


def a_doc_and_an_entity(tmp_path):
    """Set up a default vault holding a `meeting` schema, one meeting entity,
    and one ingested doc — the meeting's notes."""
    home = tmp_path / "home"
    vault_dir = tmp_path / "vault"
    source_dir = tmp_path / "source"
    for d in (home, vault_dir, source_dir):
        d.mkdir()

    assert forte(f"vault create testvault {vault_dir}", home).returncode == 0
    assert forte("schema add meeting --field date", home).returncode == 0
    assert forte('entity add meeting --name "Kickoff"', home).returncode == 0

    source = source_dir / "kickoff-notes.md"
    source.write_text("# Kickoff\n\nWe met today.\n")
    assert forte(f"doc ingest {source}", home).returncode == 0

    return home, vault_dir


# Scenario: link a document to an entity
@pytest.mark.skip(reason="TODO: implement")
def test_link_a_document_to_an_entity(tmp_path):
    # Given: a vault with one ingested doc and one entity
    # When: the user runs `forte doc link <doc_id> <entity_id>`
    # Then: the process exits with status code 0
    # Then: `forte doc show <doc_id>` lists the entity under Mentions
    ...


# Scenario: linking is reflected on the entity
# NOTE: `forte entity show` does not list linked docs yet — expected to fail
# until that lands.
@pytest.mark.skip(reason="TODO: implement; `entity show` does not list linked docs yet")
def test_linking_is_reflected_on_the_entity(tmp_path):
    # Given: a vault with one ingested doc and one entity
    # When: the user runs `forte doc link <doc_id> <entity_id>`
    # Then: `forte entity show <entity_id>` lists the doc among its linked docs
    ...


# Scenario: link a document to a nonexistent entity
@pytest.mark.skip(reason="TODO: implement")
def test_link_a_document_to_a_nonexistent_entity(tmp_path):
    # Given: a vault with one ingested doc
    # When: the user runs `forte doc link <doc_id> 999`
    # Then: we get an error
    # Then: `forte doc show <doc_id>` still shows no mentions
    ...


# Scenario: link a nonexistent document to an entity
@pytest.mark.skip(reason="TODO: implement")
def test_link_a_nonexistent_document_to_an_entity(tmp_path):
    # Given: a vault with one entity
    # When: the user runs `forte doc link 999 <entity_id>`
    # Then: we get an error
    ...


# Scenario: link a document to several entities
@pytest.mark.skip(reason="TODO: implement")
def test_link_a_document_to_several_entities(tmp_path):
    # Given: a vault with one ingested doc and two entities
    # When: the user links the doc to both entities
    # Then: `forte doc show <doc_id>` lists both entities under Mentions
    ...


# Scenario: unlink a document from an entity
@pytest.mark.skip(reason="TODO: implement")
def test_unlink_a_document_from_an_entity(tmp_path):
    # Given: a vault with a doc linked to two entities
    # When: the user runs `forte doc unlink <doc_id> <entity_id>`
    # Then: the process exits with status code 0
    # Then: `forte doc show <doc_id>` no longer lists that entity under Mentions
    # Then: `forte doc show <doc_id>` still lists the other entity
    ...


# Scenario: removing a linked entity drops the link
@pytest.mark.skip(reason="TODO: implement")
def test_removing_a_linked_entity_drops_the_link(tmp_path):
    # Given: a vault with a doc linked to an entity
    # When: the user runs `forte entity remove <entity_id> -y`
    # Then: `forte doc show <doc_id>` no longer lists that entity under Mentions
    ...


# Scenario: removing a linked document drops the link
@pytest.mark.skip(reason="TODO: implement")
def test_removing_a_linked_document_drops_the_link(tmp_path):
    # Given: a vault with a doc linked to an entity
    # When: the user runs `forte doc remove <doc_id> -y`
    # Then: `forte entity show <entity_id>` no longer references that doc
    ...

"""End-to-end tests for linking documents to entities: `forte doc link` and
`forte doc unlink`.
"""

import os
import shlex
import subprocess
import sys
from pathlib import Path

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
    """Set up a default vault holding a `meeting` schema, one meeting entity
    (#1), and one ingested doc (#1) — the meeting's notes."""
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
def test_link_a_document_to_an_entity(tmp_path):
    # Given: a vault with one ingested doc and one entity
    home, _ = a_doc_and_an_entity(tmp_path)

    # When: the user runs `forte doc link <doc_id> <entity_id>`
    result = forte("doc link 1 1", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr
    assert "Linked doc #1 to entity #1" in result.stdout

    # Then: `forte doc show <doc_id>` lists the entity under Mentions
    shown = forte("doc show 1", home)
    assert "Mentions:" in shown.stdout
    assert "entity #1 [meeting] Kickoff" in shown.stdout
    assert "Mentions: (none)" not in shown.stdout


# Scenario: linking is reflected on the entity
def test_linking_is_reflected_on_the_entity(tmp_path):
    # Given: a vault with one ingested doc and one entity
    home, _ = a_doc_and_an_entity(tmp_path)

    # When: the user runs `forte doc link <doc_id> <entity_id>`
    assert forte("doc link 1 1", home).returncode == 0

    # Then: `forte entity show <entity_id>` lists the doc among its Mentions
    shown = forte("entity show 1", home)
    assert shown.returncode == 0, shown.stderr
    assert "Mentions:" in shown.stdout
    assert "  doc #1 kickoff-notes.md" in shown.stdout


# Scenario: link a document to a nonexistent entity
def test_link_a_document_to_a_nonexistent_entity(tmp_path):
    # Given: a vault with one ingested doc
    home, _ = a_doc_and_an_entity(tmp_path)

    # When: the user runs `forte doc link <doc_id> 999`
    result = forte("doc link 1 999", home)

    # Then: we get an error
    assert result.returncode != 0
    assert "Entity #999 does not exist." in result.stderr

    # Then: `forte doc show <doc_id>` still shows no mentions
    assert "Mentions: (none)" in forte("doc show 1", home).stdout


# Scenario: link a nonexistent document to an entity
def test_link_a_nonexistent_document_to_an_entity(tmp_path):
    # Given: a vault with one entity
    home, _ = a_doc_and_an_entity(tmp_path)

    # When: the user runs `forte doc link 999 <entity_id>`
    result = forte("doc link 999 1", home)

    # Then: we get an error
    assert result.returncode != 0
    assert "Document #999 does not exist." in result.stderr


# Scenario: link a document to several entities
def test_link_a_document_to_several_entities(tmp_path):
    # Given: a vault with one ingested doc and two entities
    home, _ = a_doc_and_an_entity(tmp_path)
    assert forte("schema add person --field company", home).returncode == 0
    assert forte('entity add person --name "Ben Sivongxay"', home).returncode == 0

    # When: the user links the doc to both entities
    assert forte("doc link 1 1", home).returncode == 0
    assert forte("doc link 1 2", home).returncode == 0

    # Then: `forte doc show <doc_id>` lists both entities under Mentions
    shown = forte("doc show 1", home)
    assert "entity #1 [meeting] Kickoff" in shown.stdout
    assert "entity #2 [person] Ben Sivongxay" in shown.stdout


# Scenario: unlink a document from an entity
def test_unlink_a_document_from_an_entity(tmp_path):
    # Given: a vault with a doc linked to two entities
    home, _ = a_doc_and_an_entity(tmp_path)
    assert forte("schema add person --field company", home).returncode == 0
    assert forte('entity add person --name "Ben Sivongxay"', home).returncode == 0
    assert forte("doc link 1 1", home).returncode == 0
    assert forte("doc link 1 2", home).returncode == 0

    # When: the user runs `forte doc unlink <doc_id> <entity_id>`
    result = forte("doc unlink 1 1", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr
    assert "Unlinked doc #1 from entity #1" in result.stdout

    # Then: `forte doc show <doc_id>` no longer lists that entity under Mentions
    shown = forte("doc show 1", home)
    assert "Kickoff" not in shown.stdout.split("Mentions:")[-1]

    # Then: `forte doc show <doc_id>` still lists the other entity
    assert "entity #2 [person] Ben Sivongxay" in shown.stdout


# Scenario: removing a linked entity drops the link
def test_removing_a_linked_entity_drops_the_link(tmp_path):
    # Given: a vault with a doc linked to an entity
    home, _ = a_doc_and_an_entity(tmp_path)
    assert forte("doc link 1 1", home).returncode == 0
    assert "entity #1 [meeting] Kickoff" in forte("doc show 1", home).stdout

    # When: the user runs `forte entity remove <entity_id> -y`
    result = forte("entity remove 1 -y", home)
    assert result.returncode == 0, result.stderr

    # Then: `forte doc show <doc_id>` no longer lists that entity under Mentions
    shown = forte("doc show 1", home)
    assert shown.returncode == 0, shown.stderr
    assert "Mentions: (none)" in shown.stdout


# Scenario: removing a linked document drops the link
def test_removing_a_linked_document_drops_the_link(tmp_path):
    # Given: a vault with a doc linked to an entity
    home, _ = a_doc_and_an_entity(tmp_path)
    assert forte("doc link 1 1", home).returncode == 0
    assert "kickoff-notes.md" in forte("entity show 1", home).stdout

    # When: the user runs `forte doc remove <doc_id> -y`
    result = forte("doc remove 1 -y", home)
    assert result.returncode == 0, result.stderr

    # Then: `forte entity show <entity_id>` no longer references that doc
    shown = forte("entity show 1", home)
    assert shown.returncode == 0, shown.stderr
    assert "kickoff-notes.md" not in shown.stdout


# Scenario: an entity with no mentions shows an empty Mentions section
def test_entity_show_with_no_mentions(tmp_path):
    # Given: a vault with one entity and no linked docs
    home, _ = a_doc_and_an_entity(tmp_path)

    # When: the user runs `forte entity show <entity_id>`
    shown = forte("entity show 1", home)

    # Then: the process exits with status code 0
    assert shown.returncode == 0, shown.stderr

    # Then: the Mentions section reports none
    assert "Mentions: (none)" in shown.stdout


# Scenario: an entity mentioned by multiple documents lists them in doc-id order
def test_entity_show_with_multiple_mentions(tmp_path):
    # Given: a vault with one entity and two ingested docs, both linked to it
    home, vault_dir = a_doc_and_an_entity(tmp_path)
    source_dir = tmp_path / "source"
    second_source = source_dir / "followup-notes.md"
    second_source.write_text("# Followup\n\nWe met again.\n")
    assert forte(f"doc ingest {second_source}", home).returncode == 0
    assert forte("doc link 1 1", home).returncode == 0
    assert forte("doc link 2 1", home).returncode == 0

    # When: the user runs `forte entity show <entity_id>`
    shown = forte("entity show 1", home)

    # Then: the process exits with status code 0
    assert shown.returncode == 0, shown.stderr

    # Then: both docs are listed under Mentions, in ascending doc-id order
    assert "Mentions:" in shown.stdout
    first_pos = shown.stdout.index("doc #1 kickoff-notes.md")
    second_pos = shown.stdout.index("doc #2 followup-notes.md")
    assert first_pos < second_pos


# Scenario: unlinking a document removes it from the entity's mentions
def test_entity_show_after_unlink(tmp_path):
    # Given: a vault with one entity mentioned by one doc
    home, _ = a_doc_and_an_entity(tmp_path)
    assert forte("doc link 1 1", home).returncode == 0
    assert "  doc #1 kickoff-notes.md" in forte("entity show 1", home).stdout

    # When: the user runs `forte doc unlink <doc_id> <entity_id>`
    result = forte("doc unlink 1 1", home)
    assert result.returncode == 0, result.stderr

    # Then: `forte entity show <entity_id>` no longer lists the doc under Mentions
    shown = forte("entity show 1", home)
    assert shown.returncode == 0, shown.stderr
    assert "Mentions: (none)" in shown.stdout
    assert "kickoff-notes.md" not in shown.stdout

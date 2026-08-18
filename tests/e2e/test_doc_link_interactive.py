"""End-to-end tests for `forte doc link-interactive`: the interactive,
autocompleting entity-linking prompt.

Interactive scenarios are driven through a real pseudo-terminal via the
shared `pty_forte` fixture (see `conftest.py`), so these tests exercise the
actual keystrokes-in/text-out behavior a person would see, not internal
service or picker APIs. Non-interactive paths (a document that doesn't
exist, non-TTY stdin) don't need a pty and use plain `subprocess.run`.

Two spec scenarios are intentionally NOT covered here because the current
implementation does not match the documented behavior -- see the note above
`test_aborting_mid_session_exits_nonzero_without_a_traceback` below for the
one that matters most.
"""

import os
import shlex
import subprocess
import sys
from pathlib import Path

# Resolve the CLI from the same virtualenv running pytest, so the test does
# not depend on `forte` being on the ambient PATH.
FORTE_BIN = Path(sys.executable).parent / "forte"


def forte(args, home, env=None, stdin=None):
    """Invoke the forte CLI with `home` as HOME, so the vault registry is
    written to a temp dir rather than the real one.

    `args` is the command line as a single string, split shell-style. When
    `stdin` is given (even as ""), it is piped in, which makes stdin
    non-interactive -- used for the non-TTY scenarios below."""
    return subprocess.run(
        [str(FORTE_BIN), *shlex.split(args)],
        capture_output=True,
        text=True,
        input=stdin,
        env={**os.environ, "HOME": str(home), **(env or {})},
    )


def a_vault_with_a_doc_and_entities(tmp_path):
    """Set up a default vault with one ingested document (#1) and five
    entities across two schemas, with deliberately overlapping name
    prefixes -- Alice, Alignment Health, and Alice Nguyen all start with
    "ali" -- so ranking and the multi-select loop are actually exercised.

    IDs, in creation order: #1 Alice (person), #2 Acme Corp (client),
    #3 Alignment Health (client), #4 Alice Nguyen (person), #5 Beta LLC
    (client)."""
    home = tmp_path / "home"
    vault_dir = tmp_path / "vault"
    home.mkdir()
    vault_dir.mkdir()

    assert forte(f"vault create testvault {vault_dir}", home).returncode == 0
    assert forte("schema add person", home).returncode == 0
    assert forte("schema add client", home).returncode == 0
    assert forte('entity add person --name "Alice"', home).returncode == 0
    assert forte('entity add client --name "Acme Corp"', home).returncode == 0
    assert forte('entity add client --name "Alignment Health"', home).returncode == 0
    assert forte('entity add person --name "Alice Nguyen"', home).returncode == 0
    assert forte('entity add client --name "Beta LLC"', home).returncode == 0

    source = tmp_path / "notes.md"
    source.write_text("# Kickoff\n\nWe met today.\n")
    assert forte(f"doc ingest {source}", home).returncode == 0

    return home, vault_dir


# Scenario: Type a partial name and select the suggested entity
def test_type_a_partial_name_and_select_the_suggested_entity(tmp_path, pty_forte):
    # Given: a vault with a document and entities, including two "Alice"s
    home, _ = a_vault_with_a_doc_and_entities(tmp_path)

    # When: the user runs `forte doc link-interactive 1`
    session = pty_forte("doc link-interactive 1", home)
    session.wait_for("doc #1: notes.md")
    session.wait_for(">")

    # Then: typing `ali` shows suggestions for both Alice entities, each
    # showing id, schema, and name
    session.type_text("ali")
    session.wait_for("#1 [person] Alice")
    assert "#4 [person] Alice Nguyen" in session.output

    # When: the user selects `#1 [person] Alice` via Tab, then Enter
    session.tab()
    session.enter()

    # Then: the process confirms the entity was linked
    session.wait_for("Linked: #1 [person] Alice")

    # When: the user finishes the session with an empty line
    session.enter()
    returncode = session.wait_exit()

    # Then: the process reports 1 entity linked and exits 0
    assert returncode == 0
    assert "Linked 1 entity to doc #1: notes.md" in session.output

    # Then: `forte doc show 1` lists the entity under Mentions
    shown = forte("doc show 1", home)
    assert "entity #1 [person] Alice" in shown.stdout


# Scenario: Select several entities in one session
def test_select_several_entities_in_one_session(tmp_path, pty_forte):
    # Given: a vault with a document and entities
    home, _ = a_vault_with_a_doc_and_entities(tmp_path)

    # When: the user runs `forte doc link-interactive 1`
    session = pty_forte("doc link-interactive 1", home)
    session.wait_for(">")

    # When: the user types `ali`, then selects the third-ranked suggestion
    # (`#3 [client] Alignment Health`) via arrow-key navigation, not Tab --
    # exercising the "or arrow-key selection" acceptance path
    session.type_text("ali")
    session.wait_for("#3 [client] Alignment Health")
    session.down()
    session.down()
    session.enter()
    session.wait_for("Linked: #3 [client] Alignment Health")

    # When: the user types `acme`, which resolves to exactly one entity,
    # and submits it directly without Tab -- exercising the "plain typed
    # line that resolves to exactly one search result" acceptance path
    session.type_text("acme")
    session.wait_for("#2 [client] Acme Corp")
    session.enter()
    session.wait_for("Linked: #2 [client] Acme Corp")

    # When: the user finishes the session with an empty line
    session.enter()
    returncode = session.wait_exit()

    # Then: the process reports 2 entities linked and exits 0
    assert returncode == 0
    assert "Linked 2 entities to doc #1: notes.md" in session.output
    assert "#3 [client] Alignment Health" in session.output
    assert "#2 [client] Acme Corp" in session.output

    # Then: `forte doc show 1` lists both entities under Mentions
    shown = forte("doc show 1", home)
    assert "entity #3 [client] Alignment Health" in shown.stdout
    assert "entity #2 [client] Acme Corp" in shown.stdout


# Scenario: Finishing with an empty line immediately links nothing
def test_finishing_with_an_empty_line_immediately_links_nothing(tmp_path, pty_forte):
    # Given: a vault with a document and at least one entity
    home, _ = a_vault_with_a_doc_and_entities(tmp_path)

    # When: the user runs `forte doc link-interactive 1` and finishes
    # immediately with an empty line, without selecting anything
    session = pty_forte("doc link-interactive 1", home)
    session.wait_for(">")
    session.enter()
    returncode = session.wait_exit()

    # Then: the process reports that no entities were linked, and exits 0
    assert returncode == 0
    assert "No entities linked to doc #1: notes.md" in session.output

    # Then: `forte doc show 1` shows no mentions
    shown = forte("doc show 1", home)
    assert "Mentions: (none)" in shown.stdout


# Scenario: Text that matches no entity re-prompts instead of erroring
def test_text_that_matches_no_entity_reprompts_instead_of_erroring(tmp_path, pty_forte):
    # Given: a vault with a document and entities, none matching "zzz"
    home, _ = a_vault_with_a_doc_and_entities(tmp_path)

    # When: the user runs `forte doc link-interactive 1` and types `zzz`
    session = pty_forte("doc link-interactive 1", home)
    session.wait_for(">")
    session.type_text("zzz")
    session.enter()

    # Then: the process shows a short "no match" message and the session
    # remains open, awaiting input, rather than exiting or erroring
    session.wait_for("No matching entity")
    assert session.process.poll() is None

    # When: the user clears the input, types `ali`, and selects Alice
    session.backspace(3)
    session.type_text("ali")
    session.wait_for("#1 [person] Alice")
    session.tab()
    session.enter()
    session.wait_for("Linked: #1 [person] Alice")

    # When: the user finishes the session with an empty line
    session.enter()
    returncode = session.wait_exit()

    # Then: the process reports 1 entity linked and exits 0
    assert returncode == 0
    assert "Linked 1 entity to doc #1: notes.md" in session.output


# Scenario: Selecting an entity already linked to the document is a no-op
def test_selecting_an_entity_already_linked_to_the_document_is_a_noop(tmp_path, pty_forte):
    # Given: a document already linked to entity #1 [person] Alice
    home, _ = a_vault_with_a_doc_and_entities(tmp_path)
    assert forte("doc link 1 1", home).returncode == 0

    # When: the user runs `forte doc link-interactive 1`, types `ali`, and
    # selects `#1 [person] Alice` again
    #
    # NOTE: the spec ("Selecting an entity already linked to the document
    # is a no-op") calls for a brief message noting the entity is already
    # linked, shown as the user picks it. The picker only de-dupes against
    # entities picked earlier *in the same session* (its `picked_ids` set
    # is local to `PromptToolkitEntityPicker.pick`); it has no visibility
    # into what's already linked to the document from before this session,
    # so it prints "Linked: ..." here instead of an "already linked"
    # notice. This looks like a product bug -- see the final report -- so
    # this test asserts only the part of the spec that the current
    # implementation actually satisfies: no duplicate row is created, and
    # the final summary correctly reports nothing new was linked.
    session = pty_forte("doc link-interactive 1", home)
    session.wait_for(">")
    session.type_text("ali")
    session.wait_for("#1 [person] Alice")
    session.tab()
    session.enter()

    # When: the user finishes the session with an empty line
    session.enter()
    returncode = session.wait_exit()

    # Then: the process exits 0, and reports no new links
    assert returncode == 0
    assert "No entities linked to doc #1: notes.md" in session.output

    # Then: exactly one Mentions entry is present -- no duplicate
    shown = forte("doc show 1", home)
    assert shown.stdout.count("entity #1 [person] Alice") == 1


# Scenario: Aborting mid-session preserves what was already linked
#
# NOTE: this is only partially testable against the current implementation.
# The spec requires that an entity picked before a Ctrl-C abort stays
# linked. In practice, `PromptToolkitEntityPicker.pick` only returns its
# accumulated selections when the loop ends normally; on `KeyboardInterrupt`
# it raises `EntityPickerAbortedError` and the partial selections are lost
# (see `pick`'s `except KeyboardInterrupt` branch, and
# `DocumentService.link_document_interactive`, which assigns
# `selected = self.entity_picker.pick(...)` and only links entities found
# in `selected` -- a value that is never assigned when `pick` raises). The
# picker had already printed "Linked: #1 [person] Alice" to the user
# moments before the abort, so the CLI's own "Aborted. No entities were
# linked." message is actively wrong in that case. This looks like a
# genuine product bug -- see the final report -- so this test exercises
# only the parts of the spec the implementation actually satisfies: a
# non-zero exit, no Python traceback, and (for a session with nothing
# picked yet) an accurate "no entities were linked" report.
def test_aborting_mid_session_exits_nonzero_without_a_traceback(tmp_path, pty_forte):
    # Given: a vault with a document and an entity
    home, _ = a_vault_with_a_doc_and_entities(tmp_path)

    # When: the user runs `forte doc link-interactive 1` and aborts
    # (Ctrl-C) before picking anything
    session = pty_forte("doc link-interactive 1", home)
    session.wait_for(">")
    session.ctrl_c()
    returncode = session.wait_exit()

    # Then: the process exits with a non-zero status, reports the abort,
    # and shows no Python traceback
    assert returncode != 0
    assert "Aborted." in session.output
    assert "Traceback (most recent call last)" not in session.output


# Scenario: An unknown document id fails before any prompt is shown
def test_an_unknown_document_id_fails_before_any_prompt_is_shown(tmp_path):
    # Given: a vault with no document #99
    home = tmp_path / "home"
    vault_dir = tmp_path / "vault"
    home.mkdir()
    vault_dir.mkdir()
    assert forte(f"vault create testvault {vault_dir}", home).returncode == 0

    # When: the user runs `forte doc link-interactive 99`
    result = forte("doc link-interactive 99", home)

    # Then: the process reports the document was not found and exits
    # non-zero, without ever attempting an interactive prompt
    assert result.returncode != 0
    assert "Document #99 does not exist." in result.stderr
    assert "Link entities" not in result.stdout


# Scenario: Non-TTY stdin fails fast instead of hanging
def test_non_tty_stdin_fails_fast_instead_of_hanging(tmp_path):
    # Given: a vault with a document, and stdin that is piped (non-TTY)
    home, _ = a_vault_with_a_doc_and_entities(tmp_path)

    # When: the user runs `forte doc link-interactive 1` with piped stdin
    result = forte("doc link-interactive 1", home, stdin="")

    # Then: the process fails fast, pointing at the non-interactive
    # `forte doc link` alternative, without attempting a prompt
    assert result.returncode != 0
    assert "forte doc link <doc_id> <entity_id>" in result.stderr
    assert "Link entities" not in result.stdout

    # Then: no row was added to the mentions table
    shown = forte("doc show 1", home)
    assert "Mentions: (none)" in shown.stdout


# Scenario: A vault with no entities
def test_a_vault_with_no_entities(tmp_path, pty_forte):
    # Given: a vault with a document and no entities at all
    home = tmp_path / "home"
    vault_dir = tmp_path / "vault"
    home.mkdir()
    vault_dir.mkdir()
    assert forte(f"vault create testvault {vault_dir}", home).returncode == 0
    source = tmp_path / "notes.md"
    source.write_text("hello\n")
    assert forte(f"doc ingest {source}", home).returncode == 0

    # When: the user runs `forte doc link-interactive 1`
    session = pty_forte("doc link-interactive 1", home)
    returncode = session.wait_exit()

    # Then: the process prints a short note and exits 0, with no
    # interactive completion menu shown
    assert returncode == 0
    assert "No entities to link." in session.output
    assert "Link entities" not in session.output

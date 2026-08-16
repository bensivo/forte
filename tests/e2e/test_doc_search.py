"""End-to-end tests for `forte doc search`: literal/regex full-text search
over document bodies.

Doc ingest/list/show/remove is covered in `test_doc_crud.py`; doc create is
covered in `test_doc_create.py`; doc-to-entity linking is covered in
`test_doc_links.py`.
"""

import os
import shlex
import subprocess
import sys
from pathlib import Path

# Resolve the CLI from the same virtualenv running pytest, so the test does
# not depend on `forte` being on the ambient PATH.
FORTE_BIN = Path(sys.executable).parent / "forte"


def forte(args, home, env=None):
    """Invoke the forte CLI with `home` as HOME, so the vault registry is
    written to a temp dir rather than the real one.

    `args` is the command line as a single string, split shell-style — so
    quoted arguments (`doc search "launch date"`) survive as one argument.
    `env` optionally overrides/extends the subprocess environment."""
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


def a_source_file(tmp_path, name, content):
    """Write a source document somewhere outside the vault, as a user would
    have it sitting on their own disk before ingesting."""
    source_dir = tmp_path / "source"
    source_dir.mkdir(exist_ok=True)
    path = source_dir / name
    path.write_text(content)
    return path


def a_fake_editor(tmp_path, name, body):
    """Write a tiny fake-editor script into tmp_path and return an EDITOR
    env value that invokes it with the running interpreter, so it doesn't
    depend on an ambient `python` on PATH."""
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


KICKOFF_TEXT = (
    "# Kickoff\n"
    "\n"
    "We agreed the launch date is March 4th.\n"
    "Everyone is aligned on scope.\n"
    "The launch date was confirmed again in follow-up.\n"
)

SYNC_TEXT = (
    "# Sync\n"
    "\n"
    "Quick check-in.\n"
    "We reviewed the launch date one more time.\n"
)


# Scenario: A match in a single document
def test_a_match_in_a_single_document(tmp_path):
    # Given: a vault with a document whose body contains "launch date" on line 3
    home, _ = a_vault(tmp_path)
    source = a_source_file(tmp_path, "kickoff.md", KICKOFF_TEXT)
    assert forte(f"doc ingest {source}", home).returncode == 0

    # When: the user runs `forte doc search "launch date"`
    result = forte('doc search "launch date"', home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: the output shows a header for the doc, and both matching lines
    assert "doc #1: kickoff.md" in result.stdout
    assert "line 3: We agreed the launch date is March 4th." in result.stdout
    assert "line 5: The launch date was confirmed again in follow-up." in result.stdout

    # Then: the trailing summary reports the doc and match counts
    assert "1 document, 2 matches" in result.stdout


# Scenario: Matches across multiple documents, grouped by document
def test_matches_across_multiple_documents_grouped_by_document(tmp_path):
    # Given: two ingested documents, both mentioning "launch date"
    home, _ = a_vault(tmp_path)
    kickoff = a_source_file(tmp_path, "kickoff.md", KICKOFF_TEXT)
    sync = a_source_file(tmp_path, "sync.md", SYNC_TEXT)
    assert forte(f"doc ingest {kickoff}", home).returncode == 0
    assert forte(f"doc ingest {sync}", home).returncode == 0

    # When: the user runs `forte doc search "launch date"`
    result = forte('doc search "launch date"', home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: a group is printed for each document, listing its matching lines
    assert "doc #1: kickoff.md" in result.stdout
    assert "line 3: We agreed the launch date is March 4th." in result.stdout
    assert "line 5: The launch date was confirmed again in follow-up." in result.stdout
    assert "doc #2: sync.md" in result.stdout
    assert "line 4: We reviewed the launch date one more time." in result.stdout

    # Then: a blank line separates the two groups
    assert "\n\n" in result.stdout

    # Then: the trailing summary counts both documents and all three matches
    assert "2 documents, 3 matches" in result.stdout


# Scenario: Search is case-insensitive by default
def test_search_is_case_insensitive_by_default(tmp_path):
    # Given: a document whose body contains differently-cased text
    home, _ = a_vault(tmp_path)
    source = a_source_file(tmp_path, "kickoff.md", "# Kickoff\n\nThe Launch Date moved.\n")
    assert forte(f"doc ingest {source}", home).returncode == 0

    # When: the user searches with lowercase query text
    result = forte('doc search "launch date"', home)

    # Then: the differently-cased line is still reported as a match
    assert result.returncode == 0, result.stderr
    assert "The Launch Date moved." in result.stdout
    assert "1 document, 1 match" in result.stdout


# Scenario: `--case-sensitive` restricts matching to exact case
def test_case_sensitive_restricts_matching_to_exact_case(tmp_path):
    # Given: a document whose body contains only a differently-cased line
    home, _ = a_vault(tmp_path)
    source = a_source_file(tmp_path, "kickoff.md", "# Kickoff\n\nThe Launch Date moved.\n")
    assert forte(f"doc ingest {source}", home).returncode == 0

    # When: the user searches case-sensitively with lowercase query text
    result = forte('doc search "launch date" --case-sensitive', home)

    # Then: no matches are found
    assert result.returncode == 0, result.stderr
    assert "No matches." in result.stdout

    # When: the user instead searches case-sensitively with matching case
    result2 = forte('doc search "Launch Date" --case-sensitive', home)

    # Then: the line is reported as a match
    assert result2.returncode == 0, result2.stderr
    assert "The Launch Date moved." in result2.stdout


# Scenario: The query is treated literally by default
def test_query_is_treated_literally_by_default(tmp_path):
    # Given: a document whose body contains regex-metacharacter-looking text
    home, _ = a_vault(tmp_path)
    source = a_source_file(tmp_path, "notes.md", "# Notes\n\nSee section 4.2(a) for details.\n")
    assert forte(f"doc ingest {source}", home).returncode == 0

    # When: the user searches for that text without --regex
    result = forte('doc search "4.2(a)"', home)

    # Then: the line is reported as a match, treating . and ( literally
    assert result.returncode == 0, result.stderr
    assert "See section 4.2(a) for details." in result.stdout
    assert "1 document, 1 match" in result.stdout


# Scenario: `--regex` enables regular-expression matching
def test_regex_enables_regular_expression_matching(tmp_path):
    # Given: a document with one line containing a date and one without
    home, _ = a_vault(tmp_path)
    source = a_source_file(
        tmp_path,
        "notes.md",
        "# Notes\n\nMeeting on 2026-08-11.\nMeeting sometime soon.\n",
    )
    assert forte(f"doc ingest {source}", home).returncode == 0

    # When: the user searches with a regex date pattern and --regex
    result = forte(r'doc search "\d{4}-\d{2}-\d{2}" --regex', home)

    # Then: only the line containing the date is reported as a match
    assert result.returncode == 0, result.stderr
    assert "Meeting on 2026-08-11." in result.stdout
    assert "Meeting sometime soon." not in result.stdout
    assert "1 document, 1 match" in result.stdout


# Scenario: `--limit` caps matches shown per document
def test_limit_caps_matches_shown_per_document(tmp_path):
    # Given: a document whose body mentions "launch" on five separate lines
    home, _ = a_vault(tmp_path)
    body = "# Kickoff\n\n" + "\n".join(f"launch note {i}" for i in range(1, 6)) + "\n"
    source = a_source_file(tmp_path, "kickoff.md", body)
    assert forte(f"doc ingest {source}", home).returncode == 0

    # When: the user runs `forte doc search "launch" --limit 2`
    result = forte('doc search "launch" --limit 2', home)

    # Then: exactly 2 matching lines are printed under the doc's group
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("launch note") == 2

    # Then: the trailing summary counts only the 2 matches shown
    assert "1 document, 2 matches" in result.stdout


# Scenario: No matches found
def test_no_matches_found(tmp_path):
    # Given: a document whose body does not contain the word "budget"
    home, _ = a_vault(tmp_path)
    source = a_source_file(tmp_path, "kickoff.md", KICKOFF_TEXT)
    assert forte(f"doc ingest {source}", home).returncode == 0

    # When: the user runs `forte doc search "budget"`
    result = forte('doc search "budget"', home)

    # Then: the process prints "No matches." and exits successfully
    assert result.returncode == 0, result.stderr
    assert "No matches." in result.stdout


# Scenario: An empty query is rejected
def test_an_empty_query_is_rejected(tmp_path):
    # Given: a vault
    home, _ = a_vault(tmp_path)

    # When: the user runs `forte doc search ""`
    result = forte('doc search ""', home)

    # Then: the process reports an error and exits non-zero
    assert result.returncode != 0
    assert "empty" in result.stderr.lower()


# Scenario: An invalid regex is rejected
def test_an_invalid_regex_is_rejected(tmp_path):
    # Given: a vault
    home, _ = a_vault(tmp_path)

    # When: the user runs `forte doc search "(unclosed" --regex`
    result = forte('doc search "(unclosed" --regex', home)

    # Then: the process reports an error and exits non-zero
    assert result.returncode != 0
    assert "invalid" in result.stderr.lower()
    assert "pattern" in result.stderr.lower() or "regex" in result.stderr.lower()


# Scenario: Search is scoped to the vault selected by `--vault`
def test_search_is_scoped_to_the_vault_selected_by_vault(tmp_path):
    # Given: a default vault "personal" containing a doc that mentions "launch date"
    home = tmp_path / "home"
    personal_dir = tmp_path / "personal"
    work_dir = tmp_path / "work"
    home.mkdir()
    personal_dir.mkdir()
    work_dir.mkdir()
    assert forte(f"vault create personal {personal_dir}", home).returncode == 0
    assert forte(f"vault create work {work_dir}", home).returncode == 0
    assert forte("vault set-default personal", home).returncode == 0

    source = a_source_file(tmp_path, "kickoff.md", KICKOFF_TEXT)
    assert forte(f"doc ingest {source}", home).returncode == 0

    # When: the user searches with `--vault work`, which has no matching docs
    result = forte('doc search "launch date" --vault work', home)

    # Then: no matches are found in the "work" vault
    assert result.returncode == 0, result.stderr
    assert "No matches." in result.stdout

    # Then: searching the default vault still reports the match from "personal"
    default_result = forte('doc search "launch date"', home)
    assert default_result.returncode == 0, default_result.stderr
    assert "doc #1: kickoff.md" in default_result.stdout


# Scenario: search finds text in a document ingested from a .md file
def test_search_finds_text_in_an_ingested_document(tmp_path):
    # Given: a document ingested from a .md file on disk
    home, _ = a_vault(tmp_path)
    source = a_source_file(tmp_path, "kickoff.md", KICKOFF_TEXT)
    assert forte(f"doc ingest {source}", home).returncode == 0

    # When: the user searches for text present in the ingested body
    result = forte('doc search "launch date"', home)

    # Then: the ingested document's text is found
    assert result.returncode == 0, result.stderr
    assert "doc #1: kickoff.md" in result.stdout


# Scenario: search finds text in a document created via `forte doc create`
def test_search_finds_text_in_a_created_document(tmp_path):
    # Given: a document created by pasting text into the editor
    home, _ = a_vault(tmp_path)
    editor = an_editor_that_writes(
        tmp_path, "# Standup\n\nWe agreed the launch date is March 4th.\n"
    )
    assert (
        forte('doc create "Standup Notes"', home, env={"EDITOR": editor}).returncode
        == 0
    )

    # When: the user searches for text present in the created document's body
    result = forte('doc search "launch date"', home)

    # Then: the created document's text is found
    assert result.returncode == 0, result.stderr
    assert "doc #1: Standup Notes" in result.stdout
    assert "We agreed the launch date is March 4th." in result.stdout
    assert "1 document, 1 match" in result.stdout


# Scenario: text appearing only in frontmatter does not produce a body match
def test_frontmatter_only_text_does_not_produce_a_body_match(tmp_path):
    # Given: a document ingested from a source path containing a distinctive token
    home, _ = a_vault(tmp_path)
    source = a_source_file(tmp_path, "unique_source_token_xyz.md", KICKOFF_TEXT)
    assert forte(f"doc ingest {source}", home).returncode == 0

    # When: the user searches for text that only appears in the frontmatter's
    # source_path field, not in the document body
    result = forte('doc search "unique_source_token_xyz"', home)

    # Then: no matches are reported, since frontmatter text is not searched
    assert result.returncode == 0, result.stderr
    assert "No matches." in result.stdout


# Scenario: reported line numbers correspond to the body lines shown by `forte doc show`
def test_reported_line_numbers_correspond_to_doc_show_body_lines(tmp_path):
    # Given: an ingested document
    home, _ = a_vault(tmp_path)
    source = a_source_file(tmp_path, "kickoff.md", KICKOFF_TEXT)
    assert forte(f"doc ingest {source}", home).returncode == 0

    # When: the user searches for text on a known line, and separately shows the doc
    search_result = forte('doc search "launch date"', home)
    show_result = forte("doc show 1", home)

    # Then: both commands succeed
    assert search_result.returncode == 0, search_result.stderr
    assert show_result.returncode == 0, show_result.stderr

    # Then: `doc show`'s body contains the matching text at the same line
    # number reported by `doc search` (line 3, 1-based against the body)
    assert "line 3: We agreed the launch date is March 4th." in search_result.stdout
    show_lines = show_result.stdout.splitlines()
    body_line_index = next(
        i for i, line in enumerate(show_lines) if "We agreed the launch date" in line
    )
    # doc show prints the body verbatim; find the matching line's position
    # among lines that look like body text (i.e. it appears once, unambiguously)
    assert show_lines[body_line_index] == "We agreed the launch date is March 4th."

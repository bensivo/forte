"""End-to-end tests for the `forte schema` command group.

These will drive the real `forte` executable in a subprocess, against a
throwaway vault directory and an isolated HOME, so nothing touches the
developer's own vault registry at `~/.forte/config.yaml`.
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


# Scenario: add a schema
@pytest.mark.skip(reason="TODO: implement")
def test_add_a_schema(tmp_path):
    # Given: a vault with no schemas
    # When: the user runs `forte schema add <name> --field <field>`
    # Then: the process exits with status code 0
    # Then: the schema appears in `forte schema list`, with its fields
    ...


# Scenario: add a schema with multiple fields
@pytest.mark.skip(reason="TODO: implement")
def test_add_a_schema_with_multiple_fields(tmp_path):
    # Given: a vault with no schemas
    # When: the user runs `forte schema add <name>` with several --field flags
    # Then: the process exits with status code 0
    # Then: `forte schema list` shows all the fields, in the order declared
    ...


# Scenario: add a schema with no fields
@pytest.mark.skip(reason="TODO: implement")
def test_add_a_schema_with_no_fields(tmp_path):
    # Given: a vault with no schemas
    # When: the user runs `forte schema add <name>` with no --field flags
    # Then: the process exits with status code 0
    # Then: `forte schema list` shows the schema with no fields
    ...


# Scenario: adding a schema creates its entities folder
@pytest.mark.skip(reason="TODO: implement")
def test_adding_a_schema_creates_its_entities_folder(tmp_path):
    # Given: a vault with no schemas
    # When: the user runs `forte schema add <name>`
    # Then: the vault contains an `entities/<name>/` directory
    # Then: that is where markdown files for entities of this schema will go
    ...


# Scenario: add a schema that already exists
@pytest.mark.skip(reason="TODO: implement")
def test_add_a_schema_that_already_exists(tmp_path):
    # Given: a vault with a schema named <name>
    # When: the user runs `forte schema add <name>` again with the same name
    # Then: we get an error (schema names are unique)
    # Then: `forte schema list` still shows only one schema with that name
    # Then: the original schema's fields are unchanged
    ...


# Scenario: list schemas
@pytest.mark.skip(reason="TODO: implement")
def test_list_schemas(tmp_path):
    # Given: a vault with two schemas
    # When: the user runs `forte schema list`
    # Then: the process exits with status code 0
    # Then: the output shows both schemas and their fields
    ...


# Scenario: list schemas in an empty vault
@pytest.mark.skip(reason="TODO: implement")
def test_list_schemas_in_an_empty_vault(tmp_path):
    # Given: a vault with no schemas
    # When: the user runs `forte schema list`
    # Then: the process exits with status code 0
    # Then: the output says there are no schemas yet
    ...


# Scenario: remove a schema
@pytest.mark.skip(reason="TODO: implement")
def test_remove_a_schema(tmp_path):
    # Given: a vault with two schemas
    # When: the user runs `forte schema remove <name> -y`
    # Then: the process exits with status code 0
    # Then: `forte schema list` no longer shows that schema
    # Then: `forte schema list` still shows the other schema
    ...


# Scenario: remove a schema that does not exist
@pytest.mark.skip(reason="TODO: implement")
def test_remove_a_schema_that_does_not_exist(tmp_path):
    # Given: a vault with no schemas
    # When: the user runs `forte schema remove <name> -y`
    # Then: we get an error
    ...


# Scenario: show a schema
# NOTE: `forte schema show` is not implemented yet — this test is expected to
# fail until it is added to CliSchemaController.
@pytest.mark.skip(reason="TODO: implement; `forte schema show` does not exist yet")
def test_show_a_schema(tmp_path):
    # Given: a vault with a schema that has fields
    # When: the user runs `forte schema show <name>`
    # Then: the process exits with status code 0
    # Then: the output shows the schema name and each of its fields
    ...


# Scenario: add a field to an existing schema
# NOTE: `forte schema add-field` is not implemented yet — the solution design
# lists it as an anticipated follow-up. Expected to fail until it lands.
@pytest.mark.skip(reason="TODO: implement; `forte schema add-field` does not exist yet")
def test_add_a_field_to_an_existing_schema(tmp_path):
    # Given: a vault with a schema that has one field
    # When: the user runs `forte schema add-field <schema> <field>`
    # Then: the process exits with status code 0
    # Then: `forte schema show <schema>` lists both the old and new field
    # Then: existing entities of that schema are back-filled with an empty value
    ...


# Scenario: remove a field from an existing schema
# NOTE: `forte schema remove-field` is not implemented yet. Expected to fail
# until it lands.
@pytest.mark.skip(reason="TODO: implement; `forte schema remove-field` does not exist yet")
def test_remove_a_field_from_an_existing_schema(tmp_path):
    # Given: a vault with a schema that has two fields
    # When: the user runs `forte schema remove-field <schema> <field>`
    # Then: the process exits with status code 0
    # Then: `forte schema show <schema>` no longer lists that field
    # Then: existing entities of that schema no longer carry that field
    ...

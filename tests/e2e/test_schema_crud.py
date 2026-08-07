"""End-to-end tests for the `forte schema` command group.

These drive the real `forte` executable in a subprocess, against a
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
def test_add_a_schema(tmp_path):
    # Given: a vault with no schemas
    home, _ = a_vault(tmp_path)

    # When: the user runs `forte schema add <name> --field <field>`
    result = forte("schema add person --field company", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: the schema appears in `forte schema list`, with its fields
    listed = forte("schema list", home)
    assert "person: company" in listed.stdout


# Scenario: add a schema with multiple fields
def test_add_a_schema_with_multiple_fields(tmp_path):
    # Given: a vault with no schemas
    home, _ = a_vault(tmp_path)

    # When: the user runs `forte schema add <name>` with several --field flags
    result = forte("schema add person --field company --field title --field email", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: `forte schema list` shows all the fields, in the order declared
    listed = forte("schema list", home)
    assert "person: company, title, email" in listed.stdout


# Scenario: add a schema with no fields
def test_add_a_schema_with_no_fields(tmp_path):
    # Given: a vault with no schemas
    home, _ = a_vault(tmp_path)

    # When: the user runs `forte schema add <name>` with no --field flags
    result = forte("schema add person", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: `forte schema list` shows the schema with no fields
    listed = forte("schema list", home)
    assert "person (no fields)" in listed.stdout


# Scenario: adding a schema creates its entities folder
def test_adding_a_schema_creates_its_entities_folder(tmp_path):
    # Given: a vault with no schemas
    home, vault_dir = a_vault(tmp_path)

    # When: the user runs `forte schema add <name>`
    result = forte("schema add person --field company", home)
    assert result.returncode == 0, result.stderr

    # Then: the vault contains an `entities/<name>/` directory
    schema_dir = vault_dir / "entities" / "person"
    assert schema_dir.is_dir()

    # Then: that is where markdown files for entities of this schema will go
    assert forte('entity add person --name "Ben Sivongxay"', home).returncode == 0
    assert (schema_dir / "ben-sivongxay.md").is_file()


# Scenario: add a schema that already exists
def test_add_a_schema_that_already_exists(tmp_path):
    # Given: a vault with a schema named <name>
    home, _ = a_vault(tmp_path)
    assert forte("schema add person --field company", home).returncode == 0

    # When: the user runs `forte schema add <name>` again with the same name
    result = forte("schema add person --field title", home)

    # Then: we get an error (schema names are unique)
    assert result.returncode != 0
    assert "already exists" in result.stderr

    # Then: `forte schema list` still shows only one schema with that name
    listed = forte("schema list", home)
    assert listed.stdout.count("person") == 1

    # Then: the original schema's fields are unchanged
    assert "person: company" in listed.stdout
    assert "title" not in listed.stdout


# Scenario: list schemas
def test_list_schemas(tmp_path):
    # Given: a vault with two schemas
    home, _ = a_vault(tmp_path)
    assert forte("schema add person --field company --field title", home).returncode == 0
    assert forte("schema add project --field status", home).returncode == 0

    # When: the user runs `forte schema list`
    result = forte("schema list", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: the output shows both schemas and their fields
    assert "person: company, title" in result.stdout
    assert "project: status" in result.stdout


# Scenario: list schemas in an empty vault
def test_list_schemas_in_an_empty_vault(tmp_path):
    # Given: a vault with no schemas
    home, _ = a_vault(tmp_path)

    # When: the user runs `forte schema list`
    result = forte("schema list", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: the output says there are no schemas yet
    assert "No schemas defined yet." in result.stdout


# Scenario: remove a schema
def test_remove_a_schema(tmp_path):
    # Given: a vault with two schemas
    home, vault_dir = a_vault(tmp_path)
    assert forte("schema add person --field company", home).returncode == 0
    assert forte("schema add project --field status", home).returncode == 0

    # When: the user runs `forte schema remove <name> -y`
    result = forte("schema remove person -y", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: `forte schema list` no longer shows that schema
    listed = forte("schema list", home)
    assert "person" not in listed.stdout

    # Then: `forte schema list` still shows the other schema
    assert "project: status" in listed.stdout

    # Then: the schema's entities folder is gone, and the other one remains
    assert not (vault_dir / "entities" / "person").exists()
    assert (vault_dir / "entities" / "project").is_dir()


# Scenario: remove a schema that still has entities
def test_remove_a_schema_that_still_has_entities(tmp_path):
    # Given: a vault with a schema that has an entity
    home, _ = a_vault(tmp_path)
    assert forte("schema add person --field company", home).returncode == 0
    assert forte('entity add person --name "Ben Sivongxay"', home).returncode == 0

    # When: the user runs `forte schema remove <name> -y`
    result = forte("schema remove person -y", home)

    # Then: we get an error telling them to remove the entities first
    assert result.returncode != 0
    assert "still has entities" in result.stderr

    # Then: the schema is still there
    assert "person: company" in forte("schema list", home).stdout


# Scenario: remove a schema that does not exist
def test_remove_a_schema_that_does_not_exist(tmp_path):
    # Given: a vault with no schemas
    home, _ = a_vault(tmp_path)

    # When: the user runs `forte schema remove <name> -y`
    result = forte("schema remove person -y", home)

    # Then: we get an error
    assert result.returncode != 0
    assert "does not exist" in result.stderr


# Scenario: show a schema
# NOTE: `forte schema show` is not implemented yet. Marked strict-xfail so it
# flips to a failure — telling us to unmark it — once the command lands.
@pytest.mark.xfail(strict=True, reason="`forte schema show` is not implemented yet")
def test_show_a_schema(tmp_path):
    # Given: a vault with a schema that has fields
    home, _ = a_vault(tmp_path)
    assert forte("schema add person --field company --field title", home).returncode == 0

    # When: the user runs `forte schema show <name>`
    result = forte("schema show person", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: the output shows the schema name and each of its fields
    assert "person" in result.stdout
    assert "company" in result.stdout
    assert "title" in result.stdout


# Scenario: add a field to an existing schema
# NOTE: `forte schema add-field` is not implemented yet — the solution design
# lists it as an anticipated follow-up. Strict-xfail until it lands.
@pytest.mark.xfail(strict=True, reason="`forte schema add-field` is not implemented yet")
def test_add_a_field_to_an_existing_schema(tmp_path):
    # Given: a vault with a schema that has one field, and an entity of it
    home, vault_dir = a_vault(tmp_path)
    assert forte("schema add person --field company", home).returncode == 0
    assert forte('entity add person --name "Ben Sivongxay"', home).returncode == 0

    # When: the user runs `forte schema add-field <schema> <field>`
    result = forte("schema add-field person title", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: `forte schema list` lists both the old and new field
    assert "person: company, title" in forte("schema list", home).stdout

    # Then: existing entities of that schema are back-filled with an empty value
    entity_md = (vault_dir / "entities" / "person" / "ben-sivongxay.md").read_text()
    assert "title:" in entity_md


# Scenario: remove a field from an existing schema
# NOTE: `forte schema remove-field` is not implemented yet. Strict-xfail until
# it lands.
@pytest.mark.xfail(strict=True, reason="`forte schema remove-field` is not implemented yet")
def test_remove_a_field_from_an_existing_schema(tmp_path):
    # Given: a vault with a schema that has two fields, and an entity of it
    home, vault_dir = a_vault(tmp_path)
    assert forte("schema add person --field company --field title", home).returncode == 0
    assert (
        forte(
            'entity add person --name "Ben Sivongxay" --field company=Acme --field title=Eng',
            home,
        ).returncode
        == 0
    )

    # When: the user runs `forte schema remove-field <schema> <field>`
    result = forte("schema remove-field person title", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: `forte schema list` no longer lists that field
    listed = forte("schema list", home)
    assert "person: company" in listed.stdout
    assert "title" not in listed.stdout

    # Then: existing entities of that schema no longer carry that field
    entity_md = (vault_dir / "entities" / "person" / "ben-sivongxay.md").read_text()
    assert "title:" not in entity_md

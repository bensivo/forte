"""End-to-end tests for the `forte entity` command group.

Entities are instances of a schema, so every scenario starts from a vault
with at least one schema defined.
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
    quoted arguments (`--name "Ben Sivongxay"`) survive as one argument."""
    return subprocess.run(
        [str(FORTE_BIN), *shlex.split(args)],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(home)},
    )


def a_vault_with_schema(tmp_path):
    """Set up a home with one default vault holding a `person` schema with
    `company` and `title` fields."""
    home = tmp_path / "home"
    vault_dir = tmp_path / "vault"
    home.mkdir()
    vault_dir.mkdir()

    assert forte(f"vault create testvault {vault_dir}", home).returncode == 0
    assert (
        forte("schema add person --field company --field title", home).returncode == 0
    )
    return home, vault_dir


# Scenario: add an entity
@pytest.mark.skip(reason="TODO: implement")
def test_add_an_entity(tmp_path):
    # Given: a vault with a `person` schema
    # When: the user runs `forte entity add person --name <name>`
    # Then: the process exits with status code 0
    # Then: the output reports the new entity's id
    # Then: the entity appears in `forte entity list`
    ...


# Scenario: adding an entity writes a markdown file
@pytest.mark.skip(reason="TODO: implement")
def test_adding_an_entity_writes_a_markdown_file(tmp_path):
    # Given: a vault with a `person` schema
    # When: the user runs `forte entity add person --name <name>`
    # Then: a markdown file exists under `entities/person/`, slugified from the name
    # Then: that file's YAML frontmatter carries `name`, `aliases`, and the schema's fields
    ...


# Scenario: add an entity with field values
@pytest.mark.skip(reason="TODO: implement")
def test_add_an_entity_with_field_values(tmp_path):
    # Given: a vault with a `person` schema having `company` and `title` fields
    # When: the user runs `forte entity add person --name <name> --field company=<v> --field title=<v>
    # Then: the process exits with status code 0
    # Then: `forte entity show <id>` shows both field values
    ...


# Scenario: add an entity with aliases
@pytest.mark.skip(reason="TODO: implement")
def test_add_an_entity_with_aliases(tmp_path):
    # Given: a vault with a `person` schema
    # When: the user runs `forte entity add person --name <name> --alias <a> --alias <b>`
    # Then: the process exits with status code 0
    # Then: `forte entity show <id>` lists both aliases
    ...


# Scenario: add an entity with a field that is not in the schema
@pytest.mark.skip(reason="TODO: implement")
def test_add_an_entity_with_an_unknown_field(tmp_path):
    # Given: a vault with a `person` schema having `company` and `title` fields
    # When: the user runs `forte entity add person --name <name> --field nonsense=<v>`
    # Then: we get an error (an entity carries exactly its schema's field set)
    # Then: no entity is created — `forte entity list` is still empty
    ...


# Scenario: add an entity of a schema that does not exist
@pytest.mark.skip(reason="TODO: implement")
def test_add_an_entity_of_an_unknown_schema(tmp_path):
    # Given: a vault with a `person` schema
    # When: the user runs `forte entity add nosuchschema --name <name>`
    # Then: we get an error
    # Then: no entity is created
    ...


# Scenario: list entities
@pytest.mark.skip(reason="TODO: implement")
def test_list_entities(tmp_path):
    # Given: a vault with two entities
    # When: the user runs `forte entity list`
    # Then: the process exits with status code 0
    # Then: the output shows both entities, with their ids and schemas
    ...


# Scenario: list entities filtered by schema
@pytest.mark.skip(reason="TODO: implement")
def test_list_entities_filtered_by_schema(tmp_path):
    # Given: a vault with two schemas, and one entity of each
    # When: the user runs `forte entity list --schema <schema>`
    # Then: the process exits with status code 0
    # Then: only entities of that schema are shown
    ...


# Scenario: list entities in an empty vault
@pytest.mark.skip(reason="TODO: implement")
def test_list_entities_in_an_empty_vault(tmp_path):
    # Given: a vault with a schema but no entities
    # When: the user runs `forte entity list`
    # Then: the process exits with status code 0
    # Then: the output says there are no entities yet
    ...


# Scenario: show an entity
@pytest.mark.skip(reason="TODO: implement")
def test_show_an_entity(tmp_path):
    # Given: a vault with an entity that has aliases and field values
    # When: the user runs `forte entity show <id>`
    # Then: the process exits with status code 0
    # Then: the output shows the entity's id, name, and schema
    # Then: the output shows its aliases
    # Then: the output shows each of its field values
    ...


# Scenario: show an entity that does not exist
@pytest.mark.skip(reason="TODO: implement")
def test_show_an_entity_that_does_not_exist(tmp_path):
    # Given: a vault with no entities
    # When: the user runs `forte entity show 999`
    # Then: we get an error
    ...


# Scenario: update a field on an entity
@pytest.mark.skip(reason="TODO: implement")
def test_update_a_field_on_an_entity(tmp_path):
    # Given: a vault with an entity whose `title` field is set
    # When: the user runs `forte entity edit <id> --set title=<new value>`
    # Then: the process exits with status code 0
    # Then: `forte entity show <id>` shows the new value
    # Then: the entity's markdown frontmatter carries the new value too
    ...


# Scenario: update a field that is not in the schema
@pytest.mark.skip(reason="TODO: implement")
def test_update_a_field_that_is_not_in_the_schema(tmp_path):
    # Given: a vault with an entity of the `person` schema
    # When: the user runs `forte entity edit <id> --set nonsense=<v>`
    # Then: we get an error
    # Then: the entity's existing fields are unchanged
    ...


# Scenario: rename an entity
@pytest.mark.skip(reason="TODO: implement")
def test_rename_an_entity(tmp_path):
    # Given: a vault with an entity
    # When: the user runs `forte entity edit <id> --name <new name>`
    # Then: the process exits with status code 0
    # Then: `forte entity show <id>` shows the new name, under the same id
    ...


# Scenario: add and remove aliases on an entity
@pytest.mark.skip(reason="TODO: implement")
def test_add_and_remove_aliases_on_an_entity(tmp_path):
    # Given: a vault with an entity that has one alias
    # When: the user runs `forte entity edit <id> --add-alias <b>`
    # Then: `forte entity show <id>` lists both aliases
    # When: the user runs `forte entity edit <id> --remove-alias <b>`
    # Then: `forte entity show <id>` lists only the original alias
    ...


# Scenario: remove an entity
@pytest.mark.skip(reason="TODO: implement")
def test_remove_an_entity(tmp_path):
    # Given: a vault with two entities
    # When: the user runs `forte entity remove <id> -y`
    # Then: the process exits with status code 0
    # Then: `forte entity list` no longer shows that entity
    # Then: `forte entity list` still shows the other entity
    # Then: the entity's markdown file is gone from `entities/<schema>/`
    ...


# Scenario: remove an entity that does not exist
@pytest.mark.skip(reason="TODO: implement")
def test_remove_an_entity_that_does_not_exist(tmp_path):
    # Given: a vault with no entities
    # When: the user runs `forte entity remove 999 -y`
    # Then: we get an error
    ...

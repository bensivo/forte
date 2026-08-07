"""End-to-end tests for the `forte entity` command group.

Entities are instances of a schema, so every scenario starts from a vault
with at least one schema defined.
"""

import os
import shlex
import subprocess
import sys
from pathlib import Path

import yaml

# Resolve the CLI from the same virtualenv running pytest, so the test does
# not depend on `forte` being on the ambient PATH.
FORTE_BIN = Path(sys.executable).parent / "forte"


def forte(args, home):
    """Invoke the forte CLI with `home` as HOME, so the vault registry is
    written to a temp dir rather than the real one.

    `args` is the command line as a single string, split shell-style — so
    quoted arguments (`--name "Ben Sivoravong"`) survive as one argument."""
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


def frontmatter(path):
    """Parse the YAML frontmatter out of an entity's markdown file."""
    text = path.read_text()
    assert text.startswith("---\n"), f"no frontmatter in {path}"
    _, _, rest = text.partition("---\n")
    body, _, _ = rest.partition("\n---")
    return yaml.safe_load(body)


# Scenario: add an entity
def test_add_an_entity(tmp_path):
    # Given: a vault with a `person` schema
    home, _ = a_vault_with_schema(tmp_path)

    # When: the user runs `forte entity add person --name <name>`
    result = forte('entity add person --name "Ben Sivoravong"', home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: the output reports the new entity's id
    assert "Added entity 'Ben Sivoravong' (#1) of schema 'person'" in result.stdout

    # Then: the entity appears in `forte entity list`
    assert "#1 [person] Ben Sivoravong" in forte("entity list", home).stdout


# Scenario: adding an entity writes a markdown file
def test_adding_an_entity_writes_a_markdown_file(tmp_path):
    # Given: a vault with a `person` schema
    home, vault_dir = a_vault_with_schema(tmp_path)

    # When: the user runs `forte entity add person --name <name>`
    result = forte('entity add person --name "Ben Sivoravong"', home)
    assert result.returncode == 0, result.stderr

    # Then: a markdown file exists under `entities/person/`, slugified from the name
    entity_file = vault_dir / "entities" / "person" / "ben-sivoravong.md"
    assert entity_file.is_file()

    # Then: that file's YAML frontmatter carries `name`, `aliases`, and the schema's fields
    fm = frontmatter(entity_file)
    assert fm["name"] == "Ben Sivoravong"
    assert fm["aliases"] == []
    assert set(fm) == {"name", "aliases", "company", "title"}


# Scenario: add an entity with field values
def test_add_an_entity_with_field_values(tmp_path):
    # Given: a vault with a `person` schema having `company` and `title` fields
    home, _ = a_vault_with_schema(tmp_path)

    # When: the user runs `forte entity add person --name <name> --field company=<v> --field title=<v>`
    result = forte(
        'entity add person --name "Ben Sivoravong" --field company=Acme --field title=Engineer',
        home,
    )

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: `forte entity show <id>` shows both field values
    shown = forte("entity show 1", home)
    assert "company: Acme" in shown.stdout
    assert "title: Engineer" in shown.stdout


# Scenario: add an entity with aliases
def test_add_an_entity_with_aliases(tmp_path):
    # Given: a vault with a `person` schema
    home, _ = a_vault_with_schema(tmp_path)

    # When: the user runs `forte entity add person --name <name> --alias <a> --alias <b>`
    result = forte(
        'entity add person --name "Ben Sivoravong" --alias Ben --alias "B. Sivoravong"', home
    )

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: `forte entity show <id>` lists both aliases
    assert "Aliases: Ben, B. Sivoravong" in forte("entity show 1", home).stdout


# Scenario: add an entity with a field that is not in the schema
def test_add_an_entity_with_an_unknown_field(tmp_path):
    # Given: a vault with a `person` schema having `company` and `title` fields
    home, _ = a_vault_with_schema(tmp_path)

    # When: the user runs `forte entity add person --name <name> --field nonsense=<v>`
    result = forte('entity add person --name "Ben Sivoravong" --field nonsense=x', home)

    # Then: we get an error (an entity carries exactly its schema's field set)
    assert result.returncode != 0
    assert "Unknown field(s) for schema 'person': nonsense" in result.stderr

    # Then: no entity is created — `forte entity list` is still empty
    assert "No entities yet." in forte("entity list", home).stdout


# Scenario: add an entity of a schema that does not exist
def test_add_an_entity_of_an_unknown_schema(tmp_path):
    # Given: a vault with a `person` schema
    home, _ = a_vault_with_schema(tmp_path)

    # When: the user runs `forte entity add nosuchschema --name <name>`
    result = forte('entity add nosuchschema --name "Ben Sivoravong"', home)

    # Then: we get an error
    assert result.returncode != 0
    assert "Schema 'nosuchschema' does not exist." in result.stderr

    # Then: no entity is created
    assert "No entities yet." in forte("entity list", home).stdout


# Scenario: list entities
def test_list_entities(tmp_path):
    # Given: a vault with two entities
    home, _ = a_vault_with_schema(tmp_path)
    assert forte('entity add person --name "Ben Sivoravong"', home).returncode == 0
    assert forte('entity add person --name "Ada Lovelace"', home).returncode == 0

    # When: the user runs `forte entity list`
    result = forte("entity list", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: the output shows both entities, with their ids and schemas
    assert "#1 [person] Ben Sivoravong" in result.stdout
    assert "#2 [person] Ada Lovelace" in result.stdout


# Scenario: list entities filtered by schema
def test_list_entities_filtered_by_schema(tmp_path):
    # Given: a vault with two schemas, and one entity of each
    home, _ = a_vault_with_schema(tmp_path)
    assert forte("schema add project --field status", home).returncode == 0
    assert forte('entity add person --name "Ben Sivoravong"', home).returncode == 0
    assert forte("entity add project --name Forte", home).returncode == 0

    # When: the user runs `forte entity list --schema <schema>`
    result = forte("entity list --schema project", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: only entities of that schema are shown
    assert "#2 [project] Forte" in result.stdout
    assert "Ben Sivoravong" not in result.stdout


# Scenario: list entities in an empty vault
def test_list_entities_in_an_empty_vault(tmp_path):
    # Given: a vault with a schema but no entities
    home, _ = a_vault_with_schema(tmp_path)

    # When: the user runs `forte entity list`
    result = forte("entity list", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: the output says there are no entities yet
    assert "No entities yet." in result.stdout


# Scenario: show an entity
def test_show_an_entity(tmp_path):
    # Given: a vault with an entity that has aliases and field values
    home, _ = a_vault_with_schema(tmp_path)
    assert (
        forte(
            'entity add person --name "Ben Sivoravong" --alias Ben'
            " --field company=Acme --field title=Engineer",
            home,
        ).returncode
        == 0
    )

    # When: the user runs `forte entity show <id>`
    result = forte("entity show 1", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: the output shows the entity's id, name, and schema
    assert "#1 Ben Sivoravong (person)" in result.stdout

    # Then: the output shows its aliases
    assert "Aliases: Ben" in result.stdout

    # Then: the output shows each of its field values
    assert "company: Acme" in result.stdout
    assert "title: Engineer" in result.stdout


# Scenario: show an entity that does not exist
def test_show_an_entity_that_does_not_exist(tmp_path):
    # Given: a vault with no entities
    home, _ = a_vault_with_schema(tmp_path)

    # When: the user runs `forte entity show 999`
    result = forte("entity show 999", home)

    # Then: we get an error
    assert result.returncode != 0
    assert "Entity #999 does not exist." in result.stderr


# Scenario: update a field on an entity
def test_update_a_field_on_an_entity(tmp_path):
    # Given: a vault with an entity whose `title` field is set
    home, vault_dir = a_vault_with_schema(tmp_path)
    assert (
        forte(
            'entity add person --name "Ben Sivoravong" --field company=Acme --field title=Engineer',
            home,
        ).returncode
        == 0
    )

    # When: the user runs `forte entity edit <id> --set title=<new value>`
    result = forte("entity edit 1 --set title=Manager", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: `forte entity show <id>` shows the new value
    shown = forte("entity show 1", home)
    assert "title: Manager" in shown.stdout
    assert "title: Engineer" not in shown.stdout

    # Then: the entity's markdown frontmatter carries the new value too
    fm = frontmatter(vault_dir / "entities" / "person" / "ben-Sivoravong.md")
    assert fm["title"] == "Manager"
    # Then: the untouched field is left alone
    assert fm["company"] == "Acme"


# Scenario: update a field that is not in the schema
def test_update_a_field_that_is_not_in_the_schema(tmp_path):
    # Given: a vault with an entity of the `person` schema
    home, _ = a_vault_with_schema(tmp_path)
    assert (
        forte(
            'entity add person --name "Ben Sivoravong" --field company=Acme --field title=Engineer',
            home,
        ).returncode
        == 0
    )

    # When: the user runs `forte entity edit <id> --set nonsense=<v>`
    result = forte("entity edit 1 --set nonsense=x", home)

    # Then: we get an error
    assert result.returncode != 0
    assert "Unknown field(s) for schema 'person': nonsense" in result.stderr

    # Then: the entity's existing fields are unchanged
    shown = forte("entity show 1", home)
    assert "company: Acme" in shown.stdout
    assert "title: Engineer" in shown.stdout
    assert "nonsense" not in shown.stdout


# Scenario: rename an entity
def test_rename_an_entity(tmp_path):
    # Given: a vault with an entity
    home, vault_dir = a_vault_with_schema(tmp_path)
    assert forte('entity add person --name "Ben Sivoravong"', home).returncode == 0

    # When: the user runs `forte entity edit <id> --name <new name>`
    result = forte('entity edit 1 --name "Ben S"', home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: `forte entity show <id>` shows the new name, under the same id
    assert "#1 Ben S (person)" in forte("entity show 1", home).stdout

    # Then: the markdown file follows the new name, leaving no file behind
    person_dir = vault_dir / "entities" / "person"
    assert [p.name for p in person_dir.iterdir()] == ["ben-s.md"]


# Scenario: add and remove aliases on an entity
def test_add_and_remove_aliases_on_an_entity(tmp_path):
    # Given: a vault with an entity that has one alias
    home, _ = a_vault_with_schema(tmp_path)
    assert (
        forte('entity add person --name "Ben Sivoravong" --alias Ben', home).returncode == 0
    )

    # When: the user runs `forte entity edit <id> --add-alias <b>`
    result = forte("entity edit 1 --add-alias Bennie", home)
    assert result.returncode == 0, result.stderr

    # Then: `forte entity show <id>` lists both aliases
    assert "Aliases: Ben, Bennie" in forte("entity show 1", home).stdout

    # When: the user runs `forte entity edit <id> --remove-alias <b>`
    result = forte("entity edit 1 --remove-alias Bennie", home)
    assert result.returncode == 0, result.stderr

    # Then: `forte entity show <id>` lists only the original alias
    assert "Aliases: Ben\n" in forte("entity show 1", home).stdout


# Scenario: remove an entity
def test_remove_an_entity(tmp_path):
    # Given: a vault with two entities
    home, vault_dir = a_vault_with_schema(tmp_path)
    assert forte('entity add person --name "Ben Sivoravong"', home).returncode == 0
    assert forte('entity add person --name "Ada Lovelace"', home).returncode == 0

    # When: the user runs `forte entity remove <id> -y`
    result = forte("entity remove 1 -y", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: `forte entity list` no longer shows that entity
    listed = forte("entity list", home)
    assert "Ben Sivoravong" not in listed.stdout

    # Then: `forte entity list` still shows the other entity
    assert "#2 [person] Ada Lovelace" in listed.stdout

    # Then: the entity's markdown file is gone from `entities/<schema>/`
    person_dir = vault_dir / "entities" / "person"
    assert not (person_dir / "ben-Sivoravong.md").exists()
    assert (person_dir / "ada-lovelace.md").is_file()


# Scenario: remove an entity that does not exist
def test_remove_an_entity_that_does_not_exist(tmp_path):
    # Given: a vault with no entities
    home, _ = a_vault_with_schema(tmp_path)

    # When: the user runs `forte entity remove 999 -y`
    result = forte("entity remove 999 -y", home)

    # Then: we get an error
    assert result.returncode != 0
    assert "Entity #999 does not exist." in result.stderr

"""End-to-end tests for the `forte vault` command group.

These drive the real `forte` executable in a subprocess, against a throwaway
vault directory and an isolated HOME, so nothing touches the developer's own
vault registry at `~/.forte/config.yaml`.
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
    quoted arguments (`--name "Kickoff Notes"`) survive as one argument."""
    return subprocess.run(
        [str(FORTE_BIN), *shlex.split(args)],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(home)},
    )


def registry(home):
    """Parse the user-level vault registry at `<home>/.forte/config.yaml`."""
    return yaml.safe_load((home / ".forte" / "config.yaml").read_text())


def two_vaults(tmp_path):
    """Set up a home with two registered vaults, `vault-a` and `vault-b`.

    vault-a is created first, so it becomes the default."""
    home = tmp_path / "home"
    vault_a = tmp_path / "vault-a"
    vault_b = tmp_path / "vault-b"
    for d in (home, vault_a, vault_b):
        d.mkdir()

    assert forte(f"vault create vault-a {vault_a}", home).returncode == 0
    assert forte(f"vault create vault-b {vault_b}", home).returncode == 0
    return home, vault_a, vault_b


# Scenario: create a new vault
def test_create_a_new_vault(tmp_path):
    # Given: a user home, and vault directory with no existing vault
    # Forte writes configs to the user home - this is our fake user home for the test case
    home = tmp_path / "home"
    vault_dir = tmp_path / "vault"
    home.mkdir()
    vault_dir.mkdir()

    # When: the user runs `forte vault create <name> <dir>`
    result = forte(f"vault create testvault {vault_dir}", home)

    # Then: the process exits with status code 0
    assert result.returncode == 0, result.stderr

    # Then: the directory contains a `forte.yaml` and `forte.db` file
    assert (vault_dir / "forte.yaml").is_file()
    assert (vault_dir / "forte.db").is_file()

    # Then: the user's home directory contains a `config.yaml`
    registry_path = home / ".forte" / "config.yaml"
    assert registry_path.is_file()

    # Then: the $home/.forte/config.yaml has an entry under 'vaults'
    registry = yaml.safe_load(registry_path.read_text())
    assert registry["vaults"] == {"testvault": str(vault_dir)}


# Scenario: create a vault on existing vault folder
def test_create_a_vault_on_existing_vault_folder(tmp_path):
    # Given: a folder with an existing vault
    home = tmp_path / "home"
    vault_dir = tmp_path / "vault"
    home.mkdir()
    vault_dir.mkdir()
    assert forte(f"vault create testvault {vault_dir}", home).returncode == 0

    # When: we run `forte vault create <name> <folder>` with the same folder
    # A different name, so this exercises the target-conflict check rather
    # than tripping the duplicate-name check first.
    result = forte(f"vault create othervault {vault_dir}", home)

    # Then: we get an error
    assert result.returncode != 0
    assert "already exists" in result.stderr

    # Then: no duplicate vault entry is added to user config.yaml
    assert registry(home)["vaults"] == {"testvault": str(vault_dir)}


# Scenario: list all vaults
def test_list_all_vaults(tmp_path):
    # Given: we've created 2 vaults
    home, vault_a, vault_b = two_vaults(tmp_path)

    # When: we run `forte vault list`
    result = forte("vault list", home)

    # Then: the output shows both vaults
    assert result.returncode == 0, result.stderr
    assert f"vault-a: {vault_a}" in result.stdout
    assert f"vault-b: {vault_b}" in result.stdout


# Scenario: remove a vault
def test_remove_a_vault(tmp_path):
    # Given: we've created 2 vaults
    home, vault_a, vault_b = two_vaults(tmp_path)

    # When: we run `forte vault remove <name>`
    result = forte("vault remove vault-a -y", home)
    assert result.returncode == 0, result.stderr

    # Then: running `forte vault list` only shows the leftover vault
    listed = forte("vault list", home)
    assert "vault-b" in listed.stdout
    assert "vault-a" not in listed.stdout

    # Then: the vault is removed from user level config
    assert registry(home)["vaults"] == {"vault-b": str(vault_b)}

    # Then: the vault files persist
    assert (vault_a / "forte.yaml").is_file()
    assert (vault_a / "forte.db").is_file()


# Scenario: set default vault
def test_set_default_vault(tmp_path):
    # Given: I've created 2 vaults
    # vault-a became the default automatically, as the first one created.
    home, vault_a, vault_b = two_vaults(tmp_path)
    assert "vault-a: {} (default)".format(vault_a) in forte("vault list", home).stdout

    # When: I run `forte vault set-default <name>`
    result = forte("vault set-default vault-b", home)
    assert result.returncode == 0, result.stderr

    # Then: That vault is my new default in `forte list` output
    listed = forte("vault list", home)
    assert f"vault-b: {vault_b} (default)" in listed.stdout
    assert f"vault-a: {vault_a}" in listed.stdout
    assert "vault-a: {} (default)".format(vault_a) not in listed.stdout

    # When: I run `forte schema add <name>`
    result = forte("schema add person --field title", home)
    assert result.returncode == 0, result.stderr

    # Then: It's added to the vault that was my default (verify by looking at
    # the folder structure) — `schema add` lazily creates entities/<name>/.
    assert (vault_b / "entities" / "person").is_dir()
    assert not (vault_a / "entities" / "person").exists()
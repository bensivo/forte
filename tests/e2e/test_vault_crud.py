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


# Scenario: create a new vault
def test_vault_create(tmp_path):
    # Given: a user home, and vault directory with no existing vault
    home = tmp_path / "home"  # Forte writes configs to the user home - this is our fake user home for the test case
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


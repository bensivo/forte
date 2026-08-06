"""Unit tests for CliVaultController's `vault` Click command group, driven
with Click's CliRunner against a mock VaultService.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from click.testing import CliRunner

from forte.controller.cli_vault_controller import CliVaultController
from forte.model.vault import (
    NoDefaultVaultError,
    Vault,
    VaultAlreadyRegisteredError,
    VaultNotFoundError,
)


def _cli(mock_service: MagicMock):
    controller = CliVaultController(mock_service)
    return controller.group()


# --- create ------------------------------------------------------------------


def test_create_happy_path() -> None:
    mock_service = MagicMock()
    mock_service.create_vault.return_value = Vault(name="personal", path=Path("/Users/ben/notes"))
    cli = _cli(mock_service)

    runner = CliRunner()
    result = runner.invoke(cli, ["create", "personal", "/Users/ben/notes"])

    assert result.exit_code == 0, result.output
    assert "personal" in result.output
    assert "/Users/ben/notes" in result.output
    mock_service.create_vault.assert_called_once_with("personal", Path("/Users/ben/notes"))


def test_create_errors_map_to_click_exception() -> None:
    mock_service = MagicMock()
    mock_service.create_vault.side_effect = VaultAlreadyRegisteredError("Vault 'personal' is already registered.")
    cli = _cli(mock_service)

    runner = CliRunner()
    result = runner.invoke(cli, ["create", "personal", "/Users/ben/notes"])

    assert result.exit_code != 0
    assert "already registered" in result.output


# --- list --------------------------------------------------------------------


def test_list_marks_default() -> None:
    mock_service = MagicMock()
    mock_service.list_vaults.return_value = [
        Vault(name="personal", path=Path("/Users/ben/notes")),
        Vault(name="work", path=Path("/Users/ben/work-notes")),
    ]
    mock_service.resolve_vault.return_value = Vault(name="personal", path=Path("/Users/ben/notes"))
    cli = _cli(mock_service)

    runner = CliRunner()
    result = runner.invoke(cli, ["list"])

    assert result.exit_code == 0, result.output
    assert "personal" in result.output
    assert "work" in result.output
    personal_line = [line for line in result.output.splitlines() if "personal" in line][0]
    work_line = [line for line in result.output.splitlines() if "work" in line][0]
    assert "default" in personal_line
    assert "default" not in work_line


def test_list_empty_registry_friendly_message() -> None:
    mock_service = MagicMock()
    mock_service.list_vaults.return_value = []
    cli = _cli(mock_service)

    runner = CliRunner()
    result = runner.invoke(cli, ["list"])

    assert result.exit_code == 0, result.output
    assert "no vaults" in result.output.lower()


def test_list_with_no_default_set_still_works() -> None:
    mock_service = MagicMock()
    mock_service.list_vaults.return_value = [Vault(name="personal", path=Path("/Users/ben/notes"))]
    mock_service.resolve_vault.side_effect = NoDefaultVaultError("No default vault is set.")
    cli = _cli(mock_service)

    runner = CliRunner()
    result = runner.invoke(cli, ["list"])

    assert result.exit_code == 0, result.output
    assert "personal" in result.output
    assert "default" not in result.output


# --- show --------------------------------------------------------------------


def test_show_default_vault() -> None:
    mock_service = MagicMock()
    mock_service.get_vault.return_value = Vault(name="personal", path=Path("/Users/ben/notes"))
    mock_service.resolve_vault.return_value = Vault(name="personal", path=Path("/Users/ben/notes"))
    cli = _cli(mock_service)

    runner = CliRunner()
    result = runner.invoke(cli, ["show", "personal"])

    assert result.exit_code == 0, result.output
    assert "personal" in result.output
    assert "/Users/ben/notes" in result.output
    assert "yes" in result.output.lower()


def test_show_non_default_vault() -> None:
    mock_service = MagicMock()
    mock_service.get_vault.return_value = Vault(name="work", path=Path("/Users/ben/work-notes"))
    mock_service.resolve_vault.return_value = Vault(name="personal", path=Path("/Users/ben/notes"))
    cli = _cli(mock_service)

    runner = CliRunner()
    result = runner.invoke(cli, ["show", "work"])

    assert result.exit_code == 0, result.output
    assert "work" in result.output
    assert "no" in result.output.lower()


def test_show_unknown_vault_errors() -> None:
    mock_service = MagicMock()
    mock_service.get_vault.side_effect = VaultNotFoundError("Vault 'missing' is not registered.")
    cli = _cli(mock_service)

    runner = CliRunner()
    result = runner.invoke(cli, ["show", "missing"])

    assert result.exit_code != 0
    assert "not registered" in result.output


# --- remove ------------------------------------------------------------------


def test_remove_with_yes_skips_prompt() -> None:
    mock_service = MagicMock()
    cli = _cli(mock_service)

    runner = CliRunner()
    result = runner.invoke(cli, ["remove", "personal", "--yes"])

    assert result.exit_code == 0, result.output
    assert "personal" in result.output
    mock_service.remove_vault.assert_called_once_with("personal")


def test_remove_without_confirmation_aborts() -> None:
    mock_service = MagicMock()
    cli = _cli(mock_service)

    runner = CliRunner()
    result = runner.invoke(cli, ["remove", "personal"], input="n\n")

    assert result.exit_code == 0, result.output
    assert "Aborted." in result.output
    mock_service.remove_vault.assert_not_called()


def test_remove_with_confirmation_proceeds() -> None:
    mock_service = MagicMock()
    cli = _cli(mock_service)

    runner = CliRunner()
    result = runner.invoke(cli, ["remove", "personal"], input="y\n")

    assert result.exit_code == 0, result.output
    mock_service.remove_vault.assert_called_once_with("personal")


def test_remove_unknown_vault_errors() -> None:
    mock_service = MagicMock()
    mock_service.remove_vault.side_effect = VaultNotFoundError("Vault 'missing' is not registered.")
    cli = _cli(mock_service)

    runner = CliRunner()
    result = runner.invoke(cli, ["remove", "missing", "--yes"])

    assert result.exit_code != 0
    assert "not registered" in result.output


def test_remove_help_states_no_deletion() -> None:
    mock_service = MagicMock()
    cli = _cli(mock_service)

    runner = CliRunner()
    result = runner.invoke(cli, ["remove", "--help"])

    assert result.exit_code == 0, result.output
    assert "never deletes" in result.output or "does not delete" in result.output


# --- set-default ---------------------------------------------------------------


def test_set_default_happy_path() -> None:
    mock_service = MagicMock()
    cli = _cli(mock_service)

    runner = CliRunner()
    result = runner.invoke(cli, ["set-default", "work"])

    assert result.exit_code == 0, result.output
    assert "work" in result.output
    mock_service.set_default_vault.assert_called_once_with("work")


def test_set_default_unknown_vault_errors() -> None:
    mock_service = MagicMock()
    mock_service.set_default_vault.side_effect = VaultNotFoundError("Vault 'missing' is not registered.")
    cli = _cli(mock_service)

    runner = CliRunner()
    result = runner.invoke(cli, ["set-default", "missing"])

    assert result.exit_code != 0
    assert "not registered" in result.output

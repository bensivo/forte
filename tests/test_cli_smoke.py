from click.testing import CliRunner

from forte.cli import main


def test_cli_no_args_shows_help():
    runner = CliRunner()
    result = runner.invoke(main, [])
    assert result.exit_code == 0
    assert "Usage" in result.output
    assert "init" in result.output
    assert "hello-world" not in result.output


def test_cli_help_flag():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output
    assert "init" in result.output

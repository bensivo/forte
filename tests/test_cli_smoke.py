from click.testing import CliRunner

from forte.cli import main


def test_cli_smoke():
    runner = CliRunner()
    result = runner.invoke(main, [])
    assert result.exit_code == 0
    assert "hello-world" in result.output

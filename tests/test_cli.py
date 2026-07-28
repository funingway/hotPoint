from typer.testing import CliRunner
from hotspot.cli import app

runner = CliRunner()


def test_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.stdout
    assert "list" in result.stdout
    assert "show" in result.stdout
    assert "web" in result.stdout


def test_list_returns_empty_when_no_reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0

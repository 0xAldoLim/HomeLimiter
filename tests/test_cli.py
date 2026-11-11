from typer.testing import CliRunner

from homelimiter import cli
from homelimiter.cli import app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("doctor", "devices", "serve", "schedule-add", "emergency-restore"):
        assert command in result.output


def test_no_command_enters_terminal(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "is_interactive", lambda: True)
    launched = []

    def run(self):
        launched.append(self.control.demo)

    monkeypatch.setattr("homelimiter.tui.HomeLimiter.run", run)
    result = runner.invoke(app, ["--home", str(tmp_path), "--demo"])
    assert result.exit_code == 0, result.output
    assert launched == [True]


def test_invalid_cli_rate_is_readable(tmp_path):
    result = runner.invoke(app, ["--home", str(tmp_path), "--demo", "limit", "demo-2", "--download", "0"])
    assert result.exit_code == 1
    assert "Error:" in result.output and "0.008" in result.output and "Traceback" not in result.output


def test_demo_cli(tmp_path):
    args = ["--home", str(tmp_path), "--demo"]
    result = runner.invoke(app, [*args, "limit", "demo-2", "--download", "2", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert '"dry_run": true' in result.output
    result = runner.invoke(app, [*args, "pause", "demo-2", "--yes"])
    assert result.exit_code == 0, result.output
    assert '"simulated": true' in result.output
    result = runner.invoke(app, [*args, "resume", "demo-2"])
    assert result.exit_code == 0

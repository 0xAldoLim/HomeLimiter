from typer.testing import CliRunner

from homelimiter.cli import app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("doctor", "devices", "dashboard", "schedule-add", "emergency-restore"):
        assert command in result.output


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

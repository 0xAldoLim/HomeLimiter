import json
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import typer
from pydantic import ValidationError

from .adapters import make_adapter
from .config import initialize, load_settings, state_dir
from .control import RemoteControl
from .diagnostics import diagnose
from .models import DeviceUpdate, PolicyRequest, now
from .runtime import Runtime

app = typer.Typer(
    invoke_without_command=True, help="HomeLimiter: manage only explicitly authorized network paths."
)


def show(value):
    typer.echo(json.dumps(value, indent=2, default=str))


@contextmanager
def checked():
    try:
        yield
    except (ValueError, RuntimeError, OSError, KeyError, sqlite3.Error, subprocess.SubprocessError) as exc:
        if isinstance(exc, ValidationError):
            detail = exc.errors(include_input=False, include_url=False)[0]
            field = " / ".join(map(str, detail["loc"]))
            message = f"{field}: {detail['msg']}" if field else detail["msg"]
        elif isinstance(exc, KeyError):
            message = f"Unknown device or policy: {exc}"
        else:
            message = str(exc)
        typer.echo(f"Error: {message}", err=True)
        raise typer.Exit(1) from exc


@app.callback()
def options(
    ctx: typer.Context,
    demo: bool = typer.Option(False, help="Separate, clearly simulated demo state."),
    home: Path | None = typer.Option(None, help="State directory (or HOMELIMITER_HOME)."),
    connect: int | None = typer.Option(
        None, min=1024, max=65535, metavar="PORT", help="Use a running local headless controller."
    ),
):
    ctx.obj = {
        "demo": demo,
        "root": (home / "demo" if demo else home) if home else state_dir(demo),
        "port": connect,
    }
    if ctx.invoked_subcommand is None:
        terminal(ctx)


def is_interactive():
    return sys.stdin.isatty() and sys.stdout.isatty()


def terminal(ctx):
    if not is_interactive():
        typer.echo("Open an interactive terminal, or run 'homelimiter --help' for CLI commands.", err=True)
        raise typer.Exit(2)
    from .tui import HomeLimiter

    while True:
        with session(ctx, scheduler=True) as control:
            console = HomeLimiter(control)
            console.run()
        if not console.demo_requested:
            break
        ctx.obj = {"root": ctx.obj["root"] / "demo", "demo": True, "port": None}


@contextmanager
def session(ctx, *, refresh=False, scheduler=False):
    root, demo = ctx.obj["root"], ctx.obj["demo"]
    with checked():
        if port := ctx.obj["port"]:
            with RemoteControl(root, port) as control:
                yield control
        else:
            with Runtime(root, demo) as runtime:
                if scheduler:
                    runtime.start()
                elif refresh:
                    runtime.service.refresh()
                yield runtime.control


@app.command()
def init(ctx: typer.Context):
    """Create a private state directory and local admin credential."""
    with checked():
        initialize(ctx.obj["root"])
        load_settings(ctx.obj["root"], ctx.obj["demo"])
    typer.echo(f"Initialized {ctx.obj['root']}.")


@app.command()
def token(ctx: typer.Context):
    """Display the local headless credential. Treat terminal output as sensitive."""
    with checked():
        typer.echo(initialize(ctx.obj["root"]))


@app.command()
def check(ctx: typer.Context):
    """Validate the saved configuration and credential paths without network changes."""
    with checked():
        adapter = make_adapter(load_settings(ctx.obj["root"], ctx.obj["demo"]))
        adapter.close()
    typer.echo(f"Configuration valid: {ctx.obj['root']}")


@app.command()
def doctor(ctx: typer.Context):
    """Report OS, privileges, interfaces, routes and available Linux tools."""
    if ctx.obj["port"]:
        with session(ctx) as control:
            show(control.diagnostics())
    else:
        with checked():
            show(diagnose())


@app.command()
def devices(ctx: typer.Context):
    """List passive inventory within the authorized scope."""
    with session(ctx, refresh=True) as control:
        show([d.model_dump(mode="json") for d in control.devices()])


@app.command()
def status(ctx: typer.Context):
    """Show actual controller, enforcement and scheduler status."""
    with session(ctx) as control:
        show(control.status())


@app.command()
def capabilities(ctx: typer.Context):
    """Show operations supported by the configured adapter."""
    with session(ctx) as control:
        show(control.status()["capabilities"])


@app.command()
def adapters(ctx: typer.Context):
    """List available adapters and the configured agent's actual capabilities."""
    typer.echo("Available: readonly, mock, gateway (experimental), bridge (monitor only)")
    capabilities(ctx)


@app.command()
def agent_status(ctx: typer.Context):
    """Inspect the configured enforcement agent through its adapter."""
    capabilities(ctx)


@app.command()
def policies(ctx: typer.Context):
    """List saved policies."""
    with session(ctx) as control:
        show([p.model_dump(mode="json") for p in control.policies()])


@app.command()
def schedules(ctx: typer.Context):
    """List saved weekly, one-time and expiring policies."""
    with session(ctx) as control:
        show(
            [p.model_dump(mode="json") for p in control.policies() if p.window or p.starts_at or p.expires_at]
        )


@app.command()
def logs(ctx: typer.Context):
    """Read recent audit events."""
    with session(ctx) as control:
        show(control.logs())


def confirm_target(identifier, yes, dry_run):
    if dry_run or yes:
        return
    if not typer.confirm(f"Apply a restriction to device '{identifier}'?", default=False):
        raise typer.Abort()


def save(ctx, request):
    with session(ctx, refresh=True) as control:
        result = control.save_policy(request)
        show(result)
        if (
            not ctx.obj["port"]
            and not request.dry_run
            and not result["simulated"]
            and result["capabilities"]["adapter"] == "gateway"
        ):
            typer.echo(
                "One-shot operation: keep a terminal session or 'homelimiter serve' running "
                "to maintain the agent lease and process schedules.",
                err=True,
            )


@app.command()
def limit(
    ctx: typer.Context,
    device_id: str,
    download: float | None = typer.Option(None, help="Download cap in Mbps."),
    upload: float | None = typer.Option(None, help="Upload cap in Mbps."),
    minutes: int | None = typer.Option(
        None, min=1, max=10080, help="Automatically expire after this many minutes."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Explicitly confirm this target."),
    dry_run: bool = False,
):
    """Apply separate bandwidth caps."""
    with checked():
        request = PolicyRequest(
            device_id=device_id,
            confirm_device_id=device_id,
            download_mbps=download,
            upload_mbps=upload,
            expires_at=now() + timedelta(minutes=minutes) if minutes else None,
            dry_run=dry_run,
        )
    confirm_target(device_id, yes, dry_run)
    save(ctx, request)


@app.command()
def pause(
    ctx: typer.Context,
    device_id: str,
    minutes: int = typer.Option(30, min=1, max=10080),
    yes: bool = typer.Option(False, "--yes", "-y"),
    dry_run: bool = False,
):
    """Temporarily pause internet access for an explicit target."""
    confirm_target(device_id, yes, dry_run)
    with checked():
        request = PolicyRequest(
            device_id=device_id,
            confirm_device_id=device_id,
            blocked=True,
            expires_at=now() + timedelta(minutes=minutes),
            dry_run=dry_run,
        )
    save(ctx, request)


@app.command()
def resume(ctx: typer.Context, device_id: str):
    """Restore a device by removing all its HomeLimiter policies, including schedules."""
    with session(ctx, refresh=True) as control:
        control.resume(device_id)
        typer.echo("HomeLimiter restrictions removed.")


@app.command()
def remove(ctx: typer.Context, policy_id: str):
    """Remove one bandwidth/access/scheduled policy by exact ID."""
    with session(ctx, refresh=True) as control:
        control.remove_policy(policy_id)
        typer.echo("Policy removed.")


@app.command()
def identify(
    ctx: typer.Context,
    device_id: str,
    nickname: str | None = None,
    yes: bool = typer.Option(False, "--yes", "-y"),
    protect: bool = False,
):
    """Pin an observed identity after verifying its MAC, or protect infrastructure."""
    if not yes and not typer.confirm(f"Have you verified the identity of '{device_id}'?", default=False):
        raise typer.Abort()
    with session(ctx, refresh=True) as control:
        patch = DeviceUpdate(nickname=nickname, confirm_identity=True, protect=protect)
        show(control.update_device(device_id, patch).model_dump(mode="json"))


@app.command()
def schedule_add(
    ctx: typer.Context,
    file: Path = typer.Argument(..., exists=True, dir_okay=False),
    yes: bool = typer.Option(False, "--yes", "-y"),
    dry_run: bool = False,
):
    """Load a policy JSON file containing a weekly window or timezone-aware dates."""
    with checked():
        request = PolicyRequest.model_validate_json(file.read_text(encoding="utf-8"))
    confirm_target(request.device_id, yes, dry_run)
    request.confirm_device_id, request.dry_run = request.device_id, dry_run
    save(ctx, request)


@app.command()
def emergency_restore(ctx: typer.Context, yes: bool = typer.Option(False, "--yes", "-y")):
    """Remove desired policies and request agent recovery."""
    if not yes and not typer.confirm(
        "Remove all HomeLimiter restrictions and saved schedules?", default=False
    ):
        raise typer.Abort()
    with session(ctx) as control:
        control.emergency()
        typer.echo("HomeLimiter restrictions restored.")


def run_server(ctx, port):
    import uvicorn

    from .api import create_app

    if ctx.obj["port"]:
        raise typer.BadParameter("Use 'serve' without --connect")
    with checked(), Runtime(ctx.obj["root"], ctx.obj["demo"]) as runtime:
        typer.echo(f"Headless controller at 127.0.0.1:{port}. Keep this process running for schedules.")
        uvicorn.run(
            create_app(runtime=runtime),
            host="127.0.0.1",
            port=port,
            access_log=False,
            proxy_headers=False,
            ws="none",
        )


@app.command()
def serve(ctx: typer.Context, port: int = typer.Option(8787, min=1024, max=65535)):
    """Run the scheduler and authenticated loopback control API without a TUI."""
    run_server(ctx, port)


if __name__ == "__main__":
    app()

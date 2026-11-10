import json
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import typer

from .adapters import make_adapter
from .config import initialize, load_settings, state_dir
from .diagnostics import diagnose
from .locking import StateLock
from .models import DeviceUpdate, PolicyRequest, now
from .service import Service
from .store import Store

app = typer.Typer(no_args_is_help=True, help="HomeLimiter: manage only explicitly authorized network paths.")


def show(value):
    typer.echo(json.dumps(value, indent=2, default=str))


@app.callback()
def options(
    ctx: typer.Context,
    demo: bool = typer.Option(False, help="Separate, clearly simulated demo state."),
    home: Path | None = typer.Option(None, help="State directory (or HOMELIMITER_HOME)."),
):
    ctx.obj = {"demo": demo, "root": (home / "demo" if demo else home) if home else state_dir(demo)}


@contextmanager
def session(ctx):
    root, demo = ctx.obj["root"], ctx.obj["demo"]
    initialize(root)
    lock = StateLock(root)
    adapter = None
    try:
        adapter = make_adapter(load_settings(root, demo))
        service = Service(Store(root / "controller.db"), adapter)
        service.refresh()
        yield service
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    finally:
        if adapter and hasattr(adapter, "close"):
            adapter.close()
        lock.close()


@app.command()
def init(ctx: typer.Context):
    """Create a private state directory and local admin credential."""
    initialize(ctx.obj["root"])
    typer.echo(f"Initialized {ctx.obj['root']}. Use 'homelimiter token' to read your credential.")


@app.command()
def token(ctx: typer.Context):
    """Display the local credential. Treat terminal output as sensitive."""
    typer.echo(initialize(ctx.obj["root"]))


@app.command()
def doctor():
    """Report OS, privileges, interfaces, routes and available Linux tools."""
    show(diagnose())


@app.command()
def devices(ctx: typer.Context):
    """Refresh passive inventory within configured authorized CIDRs."""
    with session(ctx) as service:
        show([d.model_dump(mode="json") for d in service.devices()])


@app.command()
def status(ctx: typer.Context):
    with session(ctx) as service:
        show(service.status())


@app.command()
def capabilities(ctx: typer.Context):
    with session(ctx) as service:
        show(service.adapter.get_capabilities().model_dump(mode="json"))


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
    with session(ctx) as service:
        show([p.model_dump(mode="json") for p in service.store.policies()])


@app.command()
def schedules(ctx: typer.Context):
    with session(ctx) as service:
        show(
            [
                p.model_dump(mode="json")
                for p in service.store.policies()
                if p.window or p.starts_at or p.expires_at
            ]
        )


@app.command()
def logs(ctx: typer.Context):
    with session(ctx) as service:
        show(service.store.logs())


def confirm_target(identifier, yes, dry_run):
    if dry_run or yes:
        return
    if not typer.confirm(f"Apply a restriction to device '{identifier}'?", default=False):
        raise typer.Abort()


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
    """Apply separate bandwidth caps. Keep the dashboard running to reconcile schedules."""
    confirm_target(device_id, yes, dry_run)
    request = PolicyRequest(
        device_id=device_id,
        confirm_device_id=device_id,
        download_mbps=download,
        upload_mbps=upload,
        expires_at=now() + timedelta(minutes=minutes) if minutes else None,
        dry_run=dry_run,
    )
    with session(ctx) as service:
        show(service.add_policy(request))


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
    with session(ctx) as service:
        show(
            service.add_policy(
                PolicyRequest(
                    device_id=device_id,
                    confirm_device_id=device_id,
                    blocked=True,
                    expires_at=now() + timedelta(minutes=minutes),
                    dry_run=dry_run,
                )
            )
        )


@app.command()
def resume(ctx: typer.Context, device_id: str):
    """Restore a device by removing all its HomeLimiter policies, including schedules."""
    with session(ctx) as service:
        service.resume(device_id)
        typer.echo("HomeLimiter restrictions removed.")


@app.command()
def remove(ctx: typer.Context, policy_id: str):
    """Remove one bandwidth/access/scheduled policy by exact ID."""
    with session(ctx) as service:
        service.remove_policy(policy_id)
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
    with session(ctx) as service:
        show(
            service.update_device(
                device_id, DeviceUpdate(nickname=nickname, confirm_identity=True, protect=protect)
            ).model_dump(mode="json")
        )


@app.command()
def schedule_add(
    ctx: typer.Context,
    file: Path = typer.Argument(..., exists=True, dir_okay=False),
    yes: bool = typer.Option(False, "--yes", "-y"),
    dry_run: bool = False,
):
    """Load a validated PolicySpec JSON file containing a weekly window or UTC dates."""
    request = PolicyRequest.model_validate_json(file.read_text(encoding="utf-8"))
    confirm_target(request.device_id, yes, dry_run)
    request.confirm_device_id, request.dry_run = request.device_id, dry_run
    with session(ctx) as service:
        show(service.add_policy(request))


@app.command()
def emergency_restore(ctx: typer.Context, yes: bool = typer.Option(False, "--yes", "-y")):
    """Remove only HomeLimiter restrictions and future desired policies."""
    if not yes and not typer.confirm("Remove all HomeLimiter restrictions?", default=False):
        raise typer.Abort()
    with session(ctx) as service:
        service.emergency()
        typer.echo("HomeLimiter restrictions restored.")


@app.command()
def dashboard(ctx: typer.Context, port: int = typer.Option(8787, min=1024, max=65535)):
    """Start the local dashboard and persistent scheduler on 127.0.0.1."""
    import uvicorn

    from .api import create_app

    typer.echo(f"Dashboard: http://127.0.0.1:{port}; read the credential with 'homelimiter token'.")
    uvicorn.run(create_app(ctx.obj["root"], ctx.obj["demo"]), host="127.0.0.1", port=port, access_log=False)


if __name__ == "__main__":
    app()

"""Authenticated loopback control API for the optional headless runtime."""

import hmac
from contextlib import asynccontextmanager, nullcontext
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .adapters import AdapterError
from .config import state_dir
from .control import LocalControl
from .models import Confirmation, DeviceUpdate, PolicyRequest
from .runtime import Runtime
from .security import BodyLimitMiddleware
from .service import PolicyError, Service

WEB = Path(__file__).parent / "web"


def create_app(
    root: Path | None = None,
    demo=False,
    *,
    service: Service | None = None,
    token: str | None = None,
    background=True,
    runtime: Runtime | None = None,
    legacy_ui=False,
):
    root = root or state_dir(demo)

    @asynccontextmanager
    async def lifespan(app):
        with nullcontext(runtime) if runtime else Runtime(root, demo, service=service, token=token) as active:
            app.state.runtime = active
            if background:
                active.start(headless=True)
            yield

    app = FastAPI(
        title="HomeLimiter controller",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    app.add_middleware(BodyLimitMiddleware)

    @app.middleware("http")
    async def security(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
            if (origin and origin != expected) or request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse(
                    {"detail": "Cross-origin administrative request refused"}, status_code=403
                )
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse(
                    {"detail": "Administrative writes require application/json"}, status_code=415
                )
            length = request.headers.get("content-length", "0")
            if not length.isdigit() or int(length) > 65536:
                return JSONResponse({"detail": "Request too large"}, status_code=413)
        response = await call_next(request)
        response.headers.update(
            {
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
                "X-Frame-Options": "DENY",
            }
        )
        return response

    def control(request: Request) -> LocalControl:
        active = request.app.state.runtime
        authorization = request.headers.get("authorization", "")
        if not hmac.compare_digest(authorization.encode(), f"Bearer {active.token}".encode()):
            raise HTTPException(401, "Admin token required", headers={"WWW-Authenticate": "Bearer"})
        return active.control

    Control = Annotated[LocalControl, Depends(control)]

    for error, status in [(PolicyError, 409), (AdapterError, 503), (KeyError, 404)]:

        async def handler(request, exc, status=status):
            return JSONResponse({"detail": str(exc)}, status_code=status)

        app.add_exception_handler(error, handler)

    @app.get("/api/view")
    def view(ctrl: Control):
        return ctrl.view()

    @app.post("/api/refresh")
    def refresh(ctrl: Control):
        return ctrl.refresh()

    @app.get("/api/status")
    def status(ctrl: Control):
        return ctrl.status()

    @app.get("/api/devices")
    def devices(ctrl: Control):
        return ctrl.devices()

    @app.post("/api/discover")
    def discover(ctrl: Control):
        return ctrl.refresh().devices

    @app.get("/api/devices/{identifier}")
    def device(identifier: str, ctrl: Control):
        return {
            "device": ctrl.service.device(identifier),
            "stats": ctrl.service.adapter.get_bandwidth_stats(identifier),
            "policies": [p for p in ctrl.policies() if p.device_id == identifier],
        }

    @app.patch("/api/devices/{identifier}")
    def edit_device(identifier: str, patch: DeviceUpdate, ctrl: Control):
        return ctrl.update_device(identifier, patch)

    @app.post("/api/devices/{identifier}/resume")
    def resume(identifier: str, ctrl: Control):
        ctrl.resume(identifier)
        return {"restored": True, "simulated": ctrl.service.capabilities().simulated}

    @app.get("/api/policies")
    def policies(ctrl: Control):
        return ctrl.policies()

    @app.post("/api/policies")
    def add_policy(request: PolicyRequest, ctrl: Control):
        return ctrl.save_policy(request)

    @app.put("/api/policies/{identifier}")
    def edit_policy(identifier: str, request: PolicyRequest, ctrl: Control):
        return ctrl.save_policy(request, identifier)

    @app.delete("/api/policies/{identifier}")
    def delete_policy(identifier: str, ctrl: Control):
        ctrl.remove_policy(identifier)
        return {"removed": True}

    @app.get("/api/schedules")
    def schedules(ctrl: Control):
        return [p for p in ctrl.policies() if p.window or p.starts_at or p.expires_at]

    @app.get("/api/adapters")
    def adapters(ctrl: Control):
        return {
            "current": ctrl.service.capabilities(),
            "available": ["readonly", "mock", "gateway", "bridge"],
            "bridge": "Monitoring only; enforcement pending validation",
        }

    @app.get("/api/diagnostics")
    def diagnostics(ctrl: Control):
        return ctrl.diagnostics()

    @app.get("/api/logs")
    def logs(ctrl: Control):
        return ctrl.logs()

    @app.get("/api/settings")
    def settings(ctrl: Control):
        return {
            **ctrl.public_settings(),
            "adapter": ctrl.service.capabilities().adapter,
            "binding": "loopback",
            "telemetry": False,
            "configuration": "Use the local setup wizard with the headless controller stopped.",
        }

    @app.post("/api/emergency")
    def emergency(request: Confirmation, ctrl: Control):
        if not request.confirm:
            raise PolicyError("Confirm emergency restoration")
        ctrl.emergency()
        return {"restored": True}

    if legacy_ui:

        @app.get("/")
        def index():
            return FileResponse(WEB / "index.html")

        app.mount("/static", StaticFiles(directory=WEB), name="static")
    return app

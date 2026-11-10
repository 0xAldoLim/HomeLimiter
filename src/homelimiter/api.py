import asyncio
import hmac
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .adapters import AdapterError, make_adapter
from .config import Settings, initialize, load_settings, state_dir
from .diagnostics import diagnose
from .locking import StateLock
from .models import Confirmation, DeviceUpdate, PolicyRequest
from .security import BodyLimitMiddleware
from .service import PolicyError, Service
from .store import Store

WEB = Path(__file__).parent / "web"


def create_app(
    root: Path | None = None,
    demo=False,
    *,
    service: Service | None = None,
    token: str | None = None,
    background=True,
):
    root = root or state_dir(demo)
    token = token or initialize(root)
    settings = load_settings(root, demo) if service is None else Settings()
    service = service or Service(Store(root / "controller.db"), make_adapter(settings))

    @asynccontextmanager
    async def lifespan(app):
        lock = StateLock(root)
        stop = asyncio.Event()

        async def scheduler():
            while not stop.is_set():
                await asyncio.to_thread(service.tick)
                try:
                    await asyncio.wait_for(stop.wait(), timeout=15)
                except TimeoutError:
                    pass

        task = asyncio.create_task(scheduler()) if background else None
        try:
            yield
        finally:
            if task:
                stop.set()
                await task
            if hasattr(service.adapter, "close"):
                service.adapter.close()
            lock.close()

    app = FastAPI(
        title="HomeLimiter",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.service = service
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])
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

    def admin(request: Request):
        authorization = request.headers.get("authorization", "")
        if not hmac.compare_digest(authorization.encode(), f"Bearer {token}".encode()):
            raise HTTPException(401, "Admin token required", headers={"WWW-Authenticate": "Bearer"})

    for error, status in [(PolicyError, 409), (AdapterError, 503), (KeyError, 404)]:

        async def handler(request, exc, status=status):
            return JSONResponse({"detail": str(exc)}, status_code=status)

        app.add_exception_handler(error, handler)

    @app.get("/api/status", dependencies=[Depends(admin)])
    def status():
        return service.status()

    @app.get("/api/devices", dependencies=[Depends(admin)])
    def devices():
        return service.devices()

    @app.post("/api/discover", dependencies=[Depends(admin)])
    def discover():
        result = service.refresh()
        service.reconcile()
        return result

    @app.get("/api/devices/{identifier}", dependencies=[Depends(admin)])
    def device(identifier: str):
        return {
            "device": service.device(identifier),
            "stats": service.adapter.get_bandwidth_stats(identifier),
            "policies": [p for p in service.store.policies() if p.device_id == identifier],
        }

    @app.patch("/api/devices/{identifier}", dependencies=[Depends(admin)])
    def edit_device(identifier: str, patch: DeviceUpdate):
        return service.update_device(identifier, patch)

    @app.post("/api/devices/{identifier}/resume", dependencies=[Depends(admin)])
    def resume(identifier: str):
        service.resume(identifier)
        return {"restored": True, "simulated": service.adapter.get_capabilities().simulated}

    @app.get("/api/policies", dependencies=[Depends(admin)])
    def policies():
        return service.store.policies()

    @app.post("/api/policies", dependencies=[Depends(admin)])
    def add_policy(request: PolicyRequest):
        try:
            return service.add_policy(request)
        except (PolicyError, AdapterError) as exc:
            service.store.audit(
                "policy.create", "refused", {"device_id": request.device_id, "reason": str(exc)}
            )
            raise

    @app.delete("/api/policies/{identifier}", dependencies=[Depends(admin)])
    def delete_policy(identifier: str):
        service.remove_policy(identifier)
        return {"removed": True}

    @app.get("/api/schedules", dependencies=[Depends(admin)])
    def schedules():
        return [p for p in service.store.policies() if p.window or p.starts_at or p.expires_at]

    @app.get("/api/adapters", dependencies=[Depends(admin)])
    def adapters():
        return {
            "current": service.adapter.get_capabilities(),
            "available": ["readonly", "mock", "gateway", "bridge"],
            "bridge": "Monitoring only; enforcement pending validation",
        }

    @app.get("/api/diagnostics", dependencies=[Depends(admin)])
    def diagnostics():
        return diagnose()

    @app.get("/api/logs", dependencies=[Depends(admin)])
    def logs():
        return service.store.logs()

    @app.get("/api/settings", dependencies=[Depends(admin)])
    def public_settings():
        return {
            "adapter": service.adapter.get_capabilities().adapter,
            "authorized_cidrs": settings.authorized_cidrs,
            "protected_addresses": settings.protected_addresses,
            "binding": "loopback",
            "telemetry": False,
            "configuration": "Edit config.json in the state directory and restart. Secrets are never returned.",
        }

    @app.post("/api/emergency", dependencies=[Depends(admin)])
    def emergency(request: Confirmation):
        if not request.confirm:
            raise PolicyError("Confirm emergency restoration")
        service.emergency()
        return {"restored": True}

    @app.get("/")
    def index():
        return FileResponse(WEB / "index.html")

    app.mount("/static", StaticFiles(directory=WEB), name="static")
    return app

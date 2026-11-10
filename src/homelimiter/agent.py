import argparse
import asyncio
import contextlib
import hmac
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request

from .config import initialize
from .kernel import AgentConfig, LinuxEngine
from .locking import StateLock
from .models import Snapshot
from .security import BodyLimitMiddleware

log = logging.getLogger("homelimiter.agent")


def create_agent(engine: LinuxEngine, token: str):
    async def watchdog():
        while True:
            await asyncio.sleep(2)
            try:
                if await asyncio.to_thread(engine.watchdog):
                    log.warning(json.dumps({"event": "lease.expired", "result": "restored"}))
            except Exception:
                log.exception("Lease recovery failed; operator recovery required")

    @asynccontextmanager
    async def lifespan(app):
        lock = StateLock(engine.root)
        try:
            engine.recover()
            task = asyncio.create_task(watchdog())
            try:
                yield
            finally:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                engine.recover()
        finally:
            lock.close()

    app = FastAPI(
        title="HomeLimiter agent", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )

    app.add_middleware(BodyLimitMiddleware, maximum=262144)

    def admin(request: Request):
        if not hmac.compare_digest(
            request.headers.get("authorization", "").encode(), f"Bearer {token}".encode()
        ):
            raise HTTPException(401, "Agent credential required")
        if request.headers.get("origin"):
            raise HTTPException(403, "Browser requests are not accepted by the agent")

    @app.get("/v1/capabilities", dependencies=[Depends(admin)])
    def capabilities():
        return engine.capabilities()

    @app.get("/v1/devices", dependencies=[Depends(admin)])
    def devices():
        return engine.discover()

    @app.get("/v1/policies", dependencies=[Depends(admin)])
    def policies():
        with engine.lock:
            return engine.policies

    @app.put("/v1/policies", dependencies=[Depends(admin)])
    def apply(snapshot: Snapshot):
        from .adapters import AdapterError

        try:
            result = engine.apply(snapshot)
            log.info(
                json.dumps(
                    {"event": "policy.apply", "devices": len(snapshot.policies), "result": "installed"}
                )
            )
            return result
        except (AdapterError, OSError, ValueError) as exc:
            log.error(json.dumps({"event": "policy.apply", "result": "failed", "detail": str(exc)}))
            raise HTTPException(409, str(exc)) from exc

    return app


def main():
    import uvicorn

    parser = argparse.ArgumentParser(
        description="Opt-in Linux gateway agent; never provisions a network path"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--tls-cert", type=Path)
    parser.add_argument("--tls-key", type=Path)
    parser.add_argument(
        "--recover", action="store_true", help="Remove only journal-owned HomeLimiter resources and exit"
    )
    args = parser.parse_args()
    config = AgentConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
    token = initialize(args.state)
    engine = LinuxEngine(config, args.state)
    if args.recover:
        lock = StateLock(args.state)
        try:
            engine.recover()
        finally:
            lock.close()
        return
    if args.host not in {"127.0.0.1", "::1"} and not (args.tls_cert and args.tls_key):
        parser.error("Non-loopback binding requires TLS certificate and key")
    uvicorn.run(
        create_agent(engine, token),
        host=args.host,
        port=args.port,
        access_log=False,
        ssl_certfile=str(args.tls_cert) if args.tls_cert else None,
        ssl_keyfile=str(args.tls_key) if args.tls_key else None,
    )


if __name__ == "__main__":
    main()

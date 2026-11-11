"""Shared presentation-facing controller operations."""

from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from pydantic import Field

from .adapters import make_adapter
from .config import Settings, read_token, save_settings
from .diagnostics import diagnose
from .models import Device, DeviceUpdate, Effective, Model, Policy, PolicyRequest, now
from .scheduling import active, next_change
from .service import PolicyError, Service


class ScheduleState(Model):
    policy_id: str
    active: bool
    next_action: str = ""


class View(Model):
    status: dict
    devices: list[Device]
    policies: list[Policy]
    applied: list[Effective]
    logs: list[dict]
    schedules: list[ScheduleState]
    settings: dict = Field(default_factory=dict)
    scheduler: str


def schedule_states(policies: list[Policy]):
    instant = now()
    rows = []
    for policy in policies:
        if not (policy.window or policy.starts_at or policy.expires_at):
            continue
        transition = next_change(policy, instant)
        upcoming = ""
        if transition:
            moment, starting = transition
            zone = policy.window.timezone if policy.window else "UTC"
            upcoming = (
                f"{'Starts' if starting else 'Ends'} {moment.astimezone(ZoneInfo(zone)):%d %b %H:%M %Z}"
            )
        rows.append(ScheduleState(policy_id=policy.id, active=active(policy, instant), next_action=upcoming))
    return rows


class LocalControl:
    def __init__(self, service: Service, settings: Settings | None = None, root: Path | None = None):
        self.service = service
        self.settings = settings or Settings()
        self.root = root
        self.scheduler = "Running while this terminal stays open"

    @property
    def demo(self):
        return self.settings.adapter == "mock"

    @property
    def can_configure(self):
        return self.root is not None

    @property
    def needs_setup(self):
        return (
            self.can_configure and not self.settings.onboarded and (self.demo or self.settings == Settings())
        )

    def public_settings(self):
        return self.settings.model_dump(
            mode="json", exclude={"agent_token_file", "agent_url", "agent_ca_file"}
        )

    def status(self):
        return {**self.service.status(), "scheduler": self.scheduler}

    def devices(self):
        return self.service.devices()

    def policies(self):
        return self.service.store.policies()

    def logs(self):
        return self.service.store.logs()

    def view(self):
        with self.service.lock:
            status = self.service.status()
            policies = self.service.store.policies()
            return View(
                status=status,
                devices=self.service.devices(),
                policies=policies,
                applied=self.service.applied if status["acknowledged_devices"] is not None else [],
                logs=self.service.store.logs(limit=60),
                schedules=schedule_states(policies),
                settings=self.public_settings(),
                scheduler=self.scheduler,
            )

    def refresh(self):
        self.service.tick()
        return self.view()

    def diagnostics(self):
        return diagnose()

    def update_device(self, identifier: str, patch: DeviceUpdate):
        return self.service.update_device(identifier, patch)

    def save_policy(self, request: PolicyRequest, identifier: str | None = None):
        try:
            if identifier is None:
                return self.service.add_policy(request)
            return self.service.edit_policy(identifier, request)
        except (ValueError, RuntimeError, OSError) as exc:
            self.service.store.audit(
                "policy.save", "refused", {"device_id": request.device_id, "reason": str(exc)}
            )
            raise

    def remove_policy(self, identifier):
        return self.service.remove_policy(identifier)

    def resume(self, identifier):
        return self.service.resume(identifier)

    def emergency(self):
        return self.service.emergency()

    def preview(self, settings: Settings):
        adapter = make_adapter(settings)
        try:
            caps = adapter.get_capabilities()
            if settings.adapter == "gateway" and not (caps.access and caps.bandwidth):
                raise PolicyError(f"Gateway not ready: {caps.reason}")
            return adapter.discover_devices(), caps
        finally:
            adapter.close()

    def configure(self, settings: Settings, identities: dict[str, DeviceUpdate]):
        if self.root is None or self.demo != (settings.adapter == "mock"):
            raise PolicyError("Use the local terminal and the matching state profile to run setup")
        with self.service.lock:
            changed = settings.model_dump(exclude={"onboarded"}) != self.settings.model_dump(
                exclude={"onboarded"}
            )
            if changed and (self.service.store.policies() or self.service.live_attempted):
                raise PolicyError("Restore saved restrictions before changing the network scope or adapter")
            adapter = make_adapter(settings)
            previous = self.service.adapter
            try:
                caps = adapter.get_capabilities()
                if settings.adapter == "gateway" and not (caps.access and caps.bandwidth):
                    raise PolicyError(f"Gateway not ready: {caps.reason}")
                observed = adapter.discover_devices()
                # Clear old identity confirmations before changing the configured network.
                self.service.refresh(observed, reset_identities=changed)
                for identifier, patch in identities.items():
                    device = self.service.device(identifier)
                    if patch.confirm_identity and (device.status != "online" or not device.mac):
                        raise PolicyError(
                            "An identity changed before setup finished. Review the inventory again."
                        )
                save_settings(self.root, settings)
            except Exception:
                adapter.close()
                raise
            if changed:
                self.service.adapter = adapter
                self.service.reset_state()
                previous.close()
            else:
                adapter.close()
            self.settings = settings
            self.service.last_capabilities = caps
            for identifier, patch in identities.items():
                self.service.update_device(identifier, patch)
            self.service.store.audit("setup", "success", {"adapter": settings.adapter})
        return self.refresh()


class RemoteControl:
    """Access a running controller on an explicitly selected local port."""

    can_configure = False
    needs_setup = False

    def __init__(self, root: Path, port: int):
        try:
            token = read_token(root / "admin.token")
        except FileNotFoundError as exc:
            raise PolicyError(
                "Start the headless controller with the same --home and --demo options."
            ) from exc
        self.client = httpx.Client(
            base_url=f"http://127.0.0.1:{port}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
            follow_redirects=False,
            trust_env=False,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.client.close()

    def request(self, method, path, data=None):
        try:
            response = self.client.request(method, f"/api/{path}", json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                raise PolicyError("Headless credential rejected. Check --home and --demo.") from exc
            try:
                detail = exc.response.json().get("detail")
            except (ValueError, AttributeError):
                detail = None
            raise PolicyError(
                detail
                if isinstance(detail, str)
                else f"Headless controller returned HTTP {exc.response.status_code}."
            ) from exc
        except (httpx.RequestError, ValueError) as exc:
            raise PolicyError(
                "Cannot reach the headless controller. Check the port and that 'homelimiter serve' is running."
            ) from exc

    def view(self):
        return View.model_validate(self.request("GET", "view"))

    def refresh(self):
        return View.model_validate(self.request("POST", "refresh", {}))

    def status(self):
        return self.request("GET", "status")

    def devices(self):
        return [Device.model_validate(item) for item in self.request("GET", "devices")]

    def policies(self):
        return [Policy.model_validate(item) for item in self.request("GET", "policies")]

    def logs(self):
        return self.request("GET", "logs")

    def diagnostics(self):
        return self.request("GET", "diagnostics")

    def update_device(self, identifier: str, patch: DeviceUpdate):
        return Device.model_validate(
            self.request("PATCH", f"devices/{quote(identifier, safe='')}", patch.model_dump(mode="json"))
        )

    def save_policy(self, request: PolicyRequest, identifier: str | None = None):
        method, path = (
            ("PUT", f"policies/{quote(identifier, safe='')}") if identifier else ("POST", "policies")
        )
        return self.request(method, path, request.model_dump(mode="json"))

    def remove_policy(self, identifier):
        return self.request("DELETE", f"policies/{quote(identifier, safe='')}", {})

    def resume(self, identifier):
        return self.request("POST", f"devices/{quote(identifier, safe='')}/resume", {})

    def emergency(self):
        return self.request("POST", "emergency", {"confirm": True})

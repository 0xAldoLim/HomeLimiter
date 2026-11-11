import threading
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from homelimiter.adapters import AdapterError, MockAdapter
from homelimiter.api import create_app
from homelimiter.control import RemoteControl
from homelimiter.locking import StateLock
from homelimiter.models import PolicyRequest, now
from homelimiter.runtime import Runtime
from homelimiter.service import Service


class LeaseDemo(MockAdapter):
    """Simulated enforcement with the same lease lifecycle as the gateway."""

    lease_seconds = 90

    def __init__(self):
        super().__init__()
        self.calls = []
        self.applied_event = threading.Event()

    def reconcile(self, policies):
        super().reconcile(policies)
        self.calls.append(len(policies))
        if policies:
            self.applied_event.set()


def test_headless_lease_continues_after_client_disconnect(service, tmp_path):
    adapter = LeaseDemo()
    service.adapter = adapter
    service.add_policy(PolicyRequest(device_id="demo-2", confirm_device_id="demo-2", blocked=True))
    adapter.applied_event.clear()
    token = "t" * 43
    (tmp_path / "admin.token").write_text(token, encoding="utf-8")
    with Runtime(tmp_path, service=service, token=token, interval=0.02) as runtime:
        app = create_app(runtime=runtime)
        with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as client:
            with RemoteControl(tmp_path, 8787) as control:
                control.client.close()
                control.client = client
                view = control.view()
                assert view.scheduler == "Running in headless service"
                assert view.status["capabilities"]["simulated"]
                policy = view.policies[0]
                edit = PolicyRequest(device_id="demo-2", confirm_device_id="demo-2", download_mbps=3)
                assert control.save_policy(edit, policy.id)["policy"]["id"] == policy.id
                assert control.view().applied[0].download_mbps == 3
            adapter.applied_event.clear()
            assert adapter.applied_event.wait(3), "lease was not renewed after client exit"
            with pytest.raises(RuntimeError, match="State is in use"):
                StateLock(tmp_path)
    assert adapter.calls[-1] == 0
    assert not adapter.get_active_policies()
    assert service.store.policies()[0].download_mbps == 3
    StateLock(tmp_path).close()


def test_restart_applies_current_window_and_skips_missed_expiry(service):
    instant = now()
    saved = [
        PolicyRequest(
            device_id="demo-2",
            confirm_device_id="demo-2",
            blocked=True,
            starts_at=instant + timedelta(minutes=1),
            expires_at=instant + timedelta(minutes=2),
        ),
        PolicyRequest(
            device_id="demo-3",
            confirm_device_id="demo-3",
            blocked=True,
            starts_at=instant + timedelta(minutes=3),
            expires_at=instant + timedelta(minutes=5),
        ),
    ]
    for request in saved:
        service.add_policy(request)
    restarted = Service(service.store, LeaseDemo())
    restarted.tick(instant + timedelta(minutes=4))
    assert [item.device.id for item in restarted.adapter.get_active_policies()] == ["demo-3"]
    assert [p.device_id for p in restarted.store.policies()] == ["demo-3"]
    restarted.tick(instant + timedelta(minutes=6))
    assert not restarted.adapter.get_active_policies()
    assert not restarted.store.policies()


def test_discovery_failure_stops_lease_renewal(service, monkeypatch):
    adapter = LeaseDemo()
    service.adapter = adapter
    service.add_policy(PolicyRequest(device_id="demo-2", confirm_device_id="demo-2", blocked=True))
    original = adapter.discover_devices
    calls = len(adapter.calls)

    def unavailable():
        raise AdapterError("Agent connection lost")

    monkeypatch.setattr(adapter, "discover_devices", unavailable)
    service.tick()
    assert len(adapter.calls) == calls
    assert service.device("demo-2").status == "unknown"
    assert service.status()["acknowledged_devices"] is None
    assert service.status()["capabilities"]["mode"] == "MONITOR ONLY"
    monkeypatch.setattr(adapter, "discover_devices", original)
    service.tick()
    assert len(adapter.calls) == calls + 1 and service.status()["acknowledged_devices"] == 1


def test_emergency_removes_future_intent_even_if_agent_disconnected(service, monkeypatch):
    service.add_policy(PolicyRequest(device_id="demo-2", confirm_device_id="demo-2", blocked=True))

    def unavailable(policies):
        raise AdapterError("Agent connection lost")

    monkeypatch.setattr(service.adapter, "reconcile", unavailable)
    with pytest.raises(AdapterError, match="Saved policies cleared"):
        service.emergency()
    assert not service.store.policies()
    assert service.store.logs()[0]["outcome"] == "unverified"

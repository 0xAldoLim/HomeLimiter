from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from homelimiter.adapters import AdapterError, LinuxGatewayAdapter, ReadOnlyAdapter
from homelimiter.config import Settings
from homelimiter.models import DeviceUpdate, Policy, PolicyRequest, Window, now
from homelimiter.scheduling import active, next_change
from homelimiter.service import PolicyError, Service


def request(**kwargs):
    return PolicyRequest(device_id="demo-2", confirm_device_id="demo-2", download_mbps=2, **kwargs)


def test_policy_conflicts_and_expiry(service):
    service.add_policy(request(expires_at=now() + timedelta(minutes=2)))
    service.add_policy(request(upload_mbps=1, blocked=True))
    item = service.adapter.get_active_policies()[0]
    assert item.blocked and item.download_mbps == 2 and item.upload_mbps == 1
    service.reconcile(now() + timedelta(minutes=3))
    assert len(service.store.policies()) == 1


def test_confirmation_protection_and_dry_run(service):
    with pytest.raises(PolicyError, match="confirmation"):
        service.add_policy(PolicyRequest(device_id="demo-2", blocked=True))
    with pytest.raises(PolicyError, match="Protected"):
        service.add_policy(PolicyRequest(device_id="demo-1", blocked=True))
    assert service.add_policy(request(dry_run=True))["dry_run"]
    assert not service.store.policies()


def test_reconciliation_idempotent_and_restart(service):
    service.add_policy(request())
    service.reconcile()
    log_count = len(service.store.logs())
    service.reconcile()
    assert len(service.store.logs()) == log_count
    restarted = Service(service.store, type(service.adapter)())
    restarted.tick()
    assert restarted.adapter.get_active_policies()[0].download_mbps == 2


def test_failed_application_rolls_back_database(service, monkeypatch):
    service.add_policy(request())
    original = service.adapter.reconcile

    def fail_block(policies):
        if any(p.blocked for p in policies):
            raise AdapterError("injected apply failure")
        return original(policies)

    monkeypatch.setattr(service.adapter, "reconcile", fail_block)
    with pytest.raises(AdapterError):
        service.add_policy(request(blocked=True))
    assert len(service.store.policies()) == 1
    assert not service.adapter.get_active_policies()[0].blocked


def test_failed_removal_reinstalls_previous_snapshot(service, monkeypatch):
    identifier = service.add_policy(request())["policy"]["id"]
    original = service.adapter.reconcile

    def lose_ack(policies):
        original(policies)
        if not policies:
            raise AdapterError("lost acknowledgement after clear")

    monkeypatch.setattr(service.adapter, "reconcile", lose_ack)
    with pytest.raises(AdapterError, match="lost acknowledgement"):
        service.remove_policy(identifier)
    assert service.policy(identifier).download_mbps == 2
    assert service.adapter.get_active_policies()[0].download_mbps == 2


def test_gateway_projection_never_targets_stale_or_link_local_addresses(service):
    device = service.device("demo-2")
    device.addresses = ["192.0.2.42", "2001:db8::2", "fe80::2"]
    device.address_status = {"192.0.2.42": "online", "2001:db8::2": "unknown", "fe80::2": "online"}
    gateway = LinuxGatewayAdapter.__new__(LinuxGatewayAdapter)
    target = gateway.policy_target(device)
    assert list(map(str, target.addresses)) == ["192.0.2.42"]
    assert len(device.addresses) == 3


def test_monitor_cannot_apply(service):
    service.adapter = ReadOnlyAdapter(Settings())
    with pytest.raises(PolicyError, match="Passive"):
        service.add_policy(request())


def test_nickname_and_protection_persist(service):
    service.update_device("demo-2", DeviceUpdate(nickname="Television", protect=True))
    service.refresh()
    assert service.device("demo-2").nickname == "Television"
    assert service.device("demo-2").protected


def test_restore_removes_future_schedules(service):
    service.add_policy(request(starts_at=now() + timedelta(hours=1)))
    service.resume("demo-2")
    assert not service.store.policies()


@pytest.mark.parametrize(
    "instant,expected",
    [
        ("2026-11-09T14:29:00+00:00", False),
        ("2026-11-09T14:30:00+00:00", True),
        ("2026-11-09T22:29:00+00:00", True),
        ("2026-11-09T22:30:00+00:00", False),
        ("2026-11-10T14:30:00+00:00", False),
    ],
)
def test_overnight_start_day(instant, expected):
    policy = Policy(
        id="test",
        device_id="d",
        blocked=True,
        window=Window(timezone="Asia/Kuala_Lumpur", weekdays=[0], start="22:30", end="06:30"),
    )
    assert active(policy, datetime.fromisoformat(instant)) == expected


def test_dst_fall_back_both_folds():
    policy = Policy(
        id="p",
        device_id="d",
        blocked=True,
        window=Window(timezone="America/New_York", weekdays=[6], start="01:00", end="02:00"),
    )
    for hour in (5, 6):
        assert active(policy, datetime(2026, 11, 1, hour, 30, tzinfo=UTC))


def test_next_change_uses_dst_gap_transition():
    policy = Policy(
        id="p",
        device_id="d",
        blocked=True,
        window=Window(timezone="America/New_York", weekdays=[6], start="02:30", end="04:00"),
    )
    instant = datetime(2026, 3, 8, 6, tzinfo=UTC)
    assert next_change(policy, instant) == (datetime(2026, 3, 8, 7, tzinfo=UTC), True)


@pytest.mark.parametrize(
    "values",
    [
        {"download_mbps": float("nan")},
        {"upload_mbps": -1},
        {"download_mbps": 0},
        {"blocked": True, "starts_at": "2026-11-10T12:00:00"},
        {"blocked": False},
    ],
)
def test_invalid_policy(values):
    with pytest.raises(ValidationError):
        PolicyRequest(device_id="d", **values)


def test_bad_zone():
    with pytest.raises(ValidationError):
        Window(timezone="Mars/Olympus", start="10:00", end="11:00")


def test_address_collision_suspends_identity(service, monkeypatch):
    observed = service.adapter.discover_devices()
    observed[2].addresses = observed[1].addresses.copy()
    monkeypatch.setattr(service.adapter, "discover_devices", lambda: observed)
    service.refresh()
    assert service.device("demo-2").status == "ambiguous"
    assert not service.device("demo-2").confirmed
    with pytest.raises(PolicyError, match="unambiguous"):
        service.add_policy(request())


def test_renamed_identity_is_not_merged(service, monkeypatch):
    observed = service.adapter.discover_devices()
    observed[1].mac = "02:11:22:33:44:55"
    monkeypatch.setattr(service.adapter, "discover_devices", lambda: observed)
    service.refresh()
    assert not service.device("demo-2").confirmed

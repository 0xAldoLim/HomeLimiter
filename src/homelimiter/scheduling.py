from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .models import Device, Effective, Policy


def active(policy: Policy, instant: datetime) -> bool:
    if instant.tzinfo is None:
        raise ValueError("Reconciliation requires an aware instant")
    if not policy.enabled or (policy.starts_at and instant < policy.starts_at):
        return False
    if policy.expires_at and instant >= policy.expires_at:
        return False
    window = policy.window
    if window is None:
        return True
    local = instant.astimezone(ZoneInfo(window.timezone))
    clock = local.time().replace(tzinfo=None)
    if window.start < window.end:
        return local.weekday() in window.weekdays and window.start <= clock < window.end
    if clock >= window.start:
        return local.weekday() in window.weekdays
    return clock < window.end and (local - timedelta(days=1)).weekday() in window.weekdays


def effective(policies: list[Policy], devices: list[Device], instant: datetime) -> list[Effective]:
    inventory = {d.id: d for d in devices}
    result: dict[str, Effective] = {}
    for policy in policies:
        if not active(policy, instant):
            continue
        device = inventory.get(policy.device_id)
        if device is None or device.protected or not device.confirmed or device.status != "online":
            continue
        item = result.setdefault(device.id, Effective(device=device))
        item.blocked |= policy.blocked
        for key in ("download_mbps", "upload_mbps"):
            rate = getattr(policy, key)
            previous = getattr(item, key)
            if rate is not None:
                setattr(item, key, min(rate, previous) if previous is not None else rate)
    return sorted(result.values(), key=lambda item: item.device.id)

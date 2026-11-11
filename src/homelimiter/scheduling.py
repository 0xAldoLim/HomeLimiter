from datetime import UTC, datetime, timedelta
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


def next_change(policy: Policy, instant: datetime) -> tuple[datetime, bool] | None:
    """Preview the next UTC transition of one policy's window, not of the agent."""
    if not policy.enabled or (policy.expires_at and instant >= policy.expires_at):
        return None
    candidates = {value.astimezone(UTC) for value in (policy.starts_at, policy.expires_at) if value}
    if window := policy.window:
        zone = ZoneInfo(window.timezone)
        date = max(instant, policy.starts_at or instant).astimezone(zone).date()
        for days in range(-1, 9):
            for clock in (window.start, window.end):
                wall = datetime.combine(date + timedelta(days=days), clock)
                a = wall.replace(tzinfo=zone, fold=0).astimezone(UTC)
                b = wall.replace(tzinfo=zone, fold=1).astimezone(UTC)
                candidates.update((a, b))
                if a != b:
                    # A skipped or repeated wall time can change state at the offset
                    # transition itself, rather than at either local-time candidate.
                    lo, hi = sorted((int(a.timestamp()), int(b.timestamp())))
                    offset = datetime.fromtimestamp(lo, zone).utcoffset()
                    while hi - lo > 1:
                        mid = (lo + hi) // 2
                        if datetime.fromtimestamp(mid, zone).utcoffset() == offset:
                            lo = mid
                        else:
                            hi = mid
                    candidates.add(datetime.fromtimestamp(hi, UTC))
    for candidate in sorted(value for value in candidates if value > instant):
        state = active(policy, candidate)
        if active(policy, candidate - timedelta(microseconds=1)) != state:
            return candidate, state
    return None


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

import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta

from .adapters import AdapterError, RouterAdapter
from .models import Capabilities, Device, DeviceUpdate, Mode, Policy, PolicyRequest, now, snapshot_key
from .scheduling import effective
from .store import Store


class PolicyError(ValueError):
    pass


class Service:
    def __init__(self, store: Store, adapter: RouterAdapter):
        self.store, self.adapter = store, adapter
        self.lock = threading.RLock()
        self.reset_state()

    def reset_state(self):
        self.last_applied = None
        self.last_error: str | None = None
        self.last_reconciled: str | None = None
        self.last_capabilities: Capabilities | None = None
        self.applied = []
        self.lease_until = 0.0
        self.live_attempted = False
        self.inventory_failed = False

    def capabilities(self, *, probe=False):
        with self.lock:
            if probe or self.last_capabilities is None:
                self.last_capabilities = self.adapter.get_capabilities()
            return self.last_capabilities

    def refresh(self, observed: list[Device] | None = None, *, reset_identities=False):
        with self.lock:
            previous = {d.id: d for d in self.store.devices()}
            try:
                if observed is None:
                    observed = self.adapter.discover_devices()
            except (AdapterError, OSError, ValueError, RuntimeError):
                self.inventory_failed = True
                raise
            seen = set()
            address_owners: dict[str, set[str]] = {}
            for device in observed:
                seen.add(device.id)
                old = previous.get(device.id)
                if old:
                    device.nickname = old.nickname
                    device.confirmed = (
                        not reset_identities
                        and old.confirmed
                        and device.mac == old.mac
                        and device.interface == old.interface
                    )
                    device.protected |= old.protected
                    if device.status != "online":
                        device.last_seen = old.last_seen
                for address in device.addresses:
                    address_owners.setdefault(str(address), set()).add(device.id)
            for device in observed:
                if any(len(address_owners[str(a)]) > 1 for a in device.addresses):
                    device.confirmed = False
                    device.status = "ambiguous"
            missing = [d for d in previous.values() if d.id not in seen]
            for device in missing:
                device.status = "offline"
                if reset_identities:
                    device.confirmed = False
            self.store.save_devices(observed + missing)
            self.inventory_failed = False
            return self.devices()

    def devices(self) -> list[Device]:
        devices = self.store.devices()
        cutoff = now() - timedelta(minutes=5)
        for device in devices:
            if device.last_seen < cutoff:
                device.status = "offline"
            elif self.inventory_failed and device.status == "online":
                device.status = "unknown"
        return devices

    def device(self, identifier):
        device = next((d for d in self.devices() if d.id == identifier), None)
        if device is None:
            raise KeyError(identifier)
        return device

    def update_device(self, identifier: str, patch: DeviceUpdate):
        with self.lock:
            device = self.device(identifier)
            if patch.nickname:
                device.nickname = patch.nickname
            if patch.confirm_identity:
                if device.status != "online" or not device.mac:
                    raise PolicyError("Confirm a fresh, unambiguous neighbor identity")
                device.confirmed = True
            device.protected |= patch.protect
            self.store.save_device(device)
            self.store.audit("device.update", "success", {"device_id": identifier, **patch.model_dump()})
            if patch.protect or patch.confirm_identity:
                self.reconcile()
            return device

    def _desired(self, instant):
        desired = effective(self.store.policies(), self.devices(), instant)
        for item in desired:
            item.device = self.adapter.policy_target(item.device)
        return [item for item in desired if item.device.addresses or not self.adapter.lease_seconds]

    def add_policy(self, request: PolicyRequest):
        return self._save_policy(request)

    def edit_policy(self, identifier: str, request: PolicyRequest):
        with self.lock:
            previous = self.policy(identifier)
            if previous.device_id != request.device_id:
                raise PolicyError("Editing cannot change the target. Create a separate policy.")
            return self._save_policy(request, previous)

    def policy(self, identifier: str):
        policy = next((p for p in self.store.policies() if p.id == identifier), None)
        if policy is None:
            raise KeyError(identifier)
        return policy

    def _save_policy(self, request: PolicyRequest, previous: Policy | None = None):
        with self.lock:
            device = self.device(request.device_id)
            if device.protected:
                raise PolicyError("Protected infrastructure cannot be restricted")
            if not device.confirmed or device.status != "online":
                raise PolicyError("Target identity must be confirmed, online and unambiguous")
            if request.expires_at and request.expires_at <= now():
                raise PolicyError("Expiry must be in the future")
            caps = self.capabilities()
            conflicts = [
                p.id
                for p in self.store.policies()
                if p.device_id == device.id and p.enabled and (previous is None or p.id != previous.id)
            ]
            result = {
                "device_id": device.id,
                "simulated": caps.simulated,
                "conflicts": conflicts,
                "resolution": "Block wins; the lowest active rate in each direction wins.",
                "capabilities": caps.model_dump(mode="json"),
            }
            if request.dry_run:
                return {"dry_run": True, **result}
            if request.confirm_device_id != device.id:
                raise PolicyError("Explicit target-specific confirmation is required")
            if (request.blocked and not caps.access) or (
                (request.download_mbps or request.upload_mbps) and not caps.bandwidth
            ):
                raise PolicyError(caps.reason)
            if self.adapter.lease_seconds and not self.adapter.policy_target(device).addresses:
                raise PolicyError("No fresh eligible routed address is available for this target")
            policy = Policy(
                id=previous.id if previous else uuid.uuid4().hex,
                created_at=previous.created_at if previous else now(),
                **request.model_dump(exclude={"confirm_device_id", "dry_run"}),
            )
            self._change_policies([previous] if previous else [], [policy])
            self.store.audit(
                "policy.edit" if previous else "policy.create",
                "simulated" if caps.simulated else "success",
                policy.model_dump(mode="json"),
            )
            return {"policy": policy.model_dump(mode="json"), **result}

    def _change_policies(self, before: list[Policy], after: list[Policy]):
        self.store.change_policies(save=after, delete=[p.id for p in before])
        try:
            self.reconcile()
        except Exception:
            self.store.change_policies(save=before, delete=[p.id for p in after])
            try:
                # A failed acknowledgement may mean the agent changed state anyway.
                self.reconcile(force=True)
            except Exception as rollback:
                self.store.audit("policy.rollback", "failed", str(rollback))
            else:
                self.store.audit("policy.rollback", "restored", {"policies": len(before)})
            raise

    def remove_policy(self, identifier):
        with self.lock:
            self._change_policies([self.policy(identifier)], [])
            self.store.audit("policy.remove", "success", {"policy_id": identifier})

    def resume(self, identifier):
        with self.lock:
            self.device(identifier)
            removed = [p for p in self.store.policies() if p.device_id == identifier]
            self._change_policies(removed, [])
            self.store.audit("device.restore", "success", {"device_id": identifier, "removed": len(removed)})

    def reconcile(self, instant: datetime | None = None, *, force=False):
        with self.lock:
            instant = instant or now()
            desired = self._desired(instant)
            fingerprint = snapshot_key(desired)
            changed = fingerprint != self.last_applied
            try:
                if force or changed or (self.adapter.lease_seconds and (desired or self.live_attempted)):
                    # Start measuring before the request: this never overstates the remaining lease.
                    started = time.monotonic()
                    self.live_attempted |= bool(desired and self.adapter.lease_seconds)
                    self.adapter.reconcile(desired)
                    self.live_attempted = bool(desired and self.adapter.lease_seconds)
                    self.lease_until = started + self.adapter.lease_seconds if self.live_attempted else 0
                    if changed or self.last_error:
                        self.store.audit(
                            "reconcile",
                            "success",
                            {"devices": len(desired), "simulated": self.capabilities().simulated},
                        )
                self.applied = desired
                self.last_applied = fingerprint
                self.last_error = None
                self.last_reconciled = instant.isoformat()
            except (AdapterError, OSError, ValueError, RuntimeError) as exc:
                if self.last_error != str(exc):
                    self.store.audit("reconcile", "failed", str(exc))
                self.last_error = str(exc)
                raise
            expired = [p.id for p in self.store.policies() if p.expires_at and instant >= p.expires_at]
            if expired:
                self.store.change_policies(delete=expired)
                for identifier in expired:
                    self.store.audit("policy.expired", "success", {"policy_id": identifier})
            return desired

    def tick(self, instant: datetime | None = None):
        with self.lock:
            try:
                self.refresh()
                self.capabilities(probe=True)
                self.reconcile(instant)
            except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
                if self.inventory_failed and self.adapter.lease_seconds:
                    self.last_capabilities = Capabilities(
                        adapter="gateway", mode=Mode.MONITOR, reason="Agent inventory is unavailable."
                    )
                if self.last_error != str(exc):
                    self.last_error = str(exc)
                    self.store.audit("scheduler", "failed", str(exc))

    def emergency(self):
        with self.lock:
            self.store.change_policies(delete=[p.id for p in self.store.policies()])
            try:
                # Clear desired intent even if the agent cannot be reached.
                self.reconcile(force=True)
            except (OSError, ValueError, RuntimeError):
                self.store.audit(
                    "emergency.restore", "unverified", "Desired policies removed; check agent recovery"
                )
                raise
            self.store.audit("emergency.restore", "success", "All HomeLimiter desired restrictions removed")

    def suspend(self):
        """Release this runtime's live lease without deleting saved policies."""
        with self.lock:
            if self.live_attempted:
                try:
                    self.adapter.reconcile([])
                except (OSError, ValueError, RuntimeError) as exc:
                    self.store.audit("controller.stop", "unverified", str(exc))
                    raise AdapterError(
                        "Could not verify restoration; check the agent and its lease watchdog"
                    ) from exc
                self.reset_state()
                self.store.audit(
                    "controller.stop", "restored", "Released agent lease; saved policies retained"
                )

    def status(self):
        with self.lock:
            caps = self.capabilities()
            remaining = max(0, int(self.lease_until - time.monotonic())) if self.lease_until else None
            if self.last_error or (remaining is not None and remaining == 0):
                state, count = "Unverified; check activity and agent", None
            elif self.last_applied is None:
                state, count = "Not reconciled in this session", None
            elif caps.simulated:
                state, count = "Simulated only", len(self.applied)
            elif self.applied:
                state, count = "Agent acknowledged rules; traffic coverage unverified", len(self.applied)
            else:
                state, count = "No installed HomeLimiter restrictions", 0
            return {
                "capabilities": caps.model_dump(mode="json"),
                "last_error": self.last_error,
                "last_reconciled": self.last_reconciled,
                "devices": len(self.devices()),
                "policies": len(self.store.policies()),
                "enforcement": state,
                "acknowledged_devices": count,
                "lease_remaining_seconds": remaining,
                "statistics": "Unavailable; no per-device traffic measurements",
            }

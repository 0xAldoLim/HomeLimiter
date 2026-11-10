import json
import threading
import uuid
from datetime import datetime, timedelta

from .adapters import AdapterError, RouterAdapter
from .models import Device, DeviceUpdate, Policy, PolicyRequest, now
from .scheduling import effective
from .store import Store


class PolicyError(ValueError):
    pass


class Service:
    def __init__(self, store: Store, adapter: RouterAdapter):
        self.store, self.adapter = store, adapter
        self.lock = threading.RLock()
        self.last_applied = None
        self.last_error: str | None = None
        self.last_reconciled: str | None = None

    def refresh(self):
        with self.lock:
            previous = {d.id: d for d in self.store.devices()}
            observed = self.adapter.discover_devices()
            seen = set()
            address_owners: dict[str, set[str]] = {}
            for device in observed:
                seen.add(device.id)
                old = previous.get(device.id)
                if old:
                    device.nickname = old.nickname
                    device.confirmed = (
                        old.confirmed and device.mac == old.mac and device.interface == old.interface
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
                self.store.save_device(device)
            for device in previous.values():
                if device.id not in seen:
                    device.status = "offline"
                    self.store.save_device(device)
            return self.devices()

    def devices(self) -> list[Device]:
        devices = self.store.devices()
        for device in devices:
            if now() - device.last_seen > timedelta(minutes=5):
                device.status = "offline"
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
            self.reconcile()
            return device

    def _desired(self, instant):
        return effective(self.store.policies(), self.devices(), instant)

    def add_policy(self, request: PolicyRequest):
        with self.lock:
            device = self.device(request.device_id)
            if device.protected:
                raise PolicyError("Protected infrastructure cannot be restricted")
            if not device.confirmed or device.status != "online":
                raise PolicyError("Target identity must be confirmed, online and unambiguous")
            if request.expires_at and request.expires_at <= now():
                raise PolicyError("Expiry must be in the future")
            caps = self.adapter.get_capabilities()
            conflicts = [p.id for p in self.store.policies() if p.device_id == device.id and p.enabled]
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
            policy = Policy(
                id=uuid.uuid4().hex, **request.model_dump(exclude={"confirm_device_id", "dry_run"})
            )
            self.store.save_policy(policy)
            try:
                self.reconcile()
            except Exception:
                self.store.delete_policy(policy.id)
                try:
                    self.reconcile()
                except Exception as rollback:
                    self.store.audit("policy.rollback", "failed", str(rollback))
                raise
            self.store.audit(
                "policy.create", "simulated" if caps.simulated else "success", policy.model_dump(mode="json")
            )
            return {"policy": policy.model_dump(mode="json"), **result}

    def remove_policy(self, identifier):
        with self.lock:
            policy = next((p for p in self.store.policies() if p.id == identifier), None)
            if not policy:
                raise KeyError(identifier)
            self.store.delete_policy(identifier)
            try:
                self.reconcile()
            except Exception:
                self.store.save_policy(policy)
                raise
            self.store.audit("policy.remove", "success", {"policy_id": identifier})

    def resume(self, identifier):
        with self.lock:
            self.device(identifier)
            removed = [p for p in self.store.policies() if p.device_id == identifier]
            for policy in removed:
                self.store.delete_policy(policy.id)
            try:
                self.reconcile()
            except Exception:
                for policy in removed:
                    self.store.save_policy(policy)
                raise
            self.store.audit("device.restore", "success", {"device_id": identifier, "removed": len(removed)})

    def reconcile(self, instant: datetime | None = None):
        with self.lock:
            instant = instant or now()
            desired = self._desired(instant)
            # Exclude observation timestamps from identity of an effective snapshot.
            fingerprint = json.dumps(
                [p.model_dump(mode="json", exclude={"device": {"last_seen"}}) for p in desired],
                sort_keys=True,
            )
            try:
                # Remote agents need a lease renewal even when the desired state is identical.
                if fingerprint != self.last_applied or self.adapter.get_capabilities().adapter == "gateway":
                    self.adapter.reconcile(desired)
                    self.store.audit(
                        "reconcile",
                        "success",
                        {"devices": len(desired), "simulated": self.adapter.get_capabilities().simulated},
                    )
                self.last_applied = fingerprint
                self.last_error = None
                self.last_reconciled = instant.isoformat()
            except (AdapterError, OSError, ValueError) as exc:
                if self.last_error != str(exc):
                    self.store.audit("reconcile", "failed", str(exc))
                self.last_error = str(exc)
                raise
            for policy in self.store.policies():
                if policy.expires_at and instant >= policy.expires_at:
                    self.store.delete_policy(policy.id)
                    self.store.audit("policy.expired", "success", {"policy_id": policy.id})
            return desired

    def tick(self):
        try:
            self.refresh()
            self.reconcile()
        except Exception as exc:
            if self.last_error != str(exc):
                self.store.audit("scheduler", "failed", str(exc))
            self.last_error = str(exc)

    def emergency(self):
        with self.lock:
            self.adapter.reconcile([])
            for policy in self.store.policies():
                self.store.delete_policy(policy.id)
            self.last_applied = None
            self.store.audit("emergency.restore", "success", "All HomeLimiter desired restrictions removed")

    def status(self):
        caps = self.adapter.get_capabilities()
        return {
            "capabilities": caps.model_dump(mode="json"),
            "last_error": self.last_error,
            "last_reconciled": self.last_reconciled,
            "devices": len(self.devices()),
            "policies": len(self.store.policies()),
            "statistics": "Unavailable; no traffic measurements fabricated",
        }

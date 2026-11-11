import hashlib
import ipaddress
import json
import ssl
from abc import ABC, abstractmethod
from pathlib import Path

import httpx
import psutil
from pydantic import ValidationError

from .config import Settings, read_token
from .diagnostics import neighbors
from .models import Capabilities, Device, Effective, Mode, Snapshot


class AdapterError(RuntimeError):
    pass


class RouterAdapter(ABC):
    """Brand-independent interface; mutations replace a complete desired snapshot."""

    lease_seconds = 0

    def policy_target(self, device: Device) -> Device:
        return device

    def close(self):  # noqa: B027 - most adapters have no resources to release
        """Release adapter resources, if any."""

    @abstractmethod
    def discover_devices(self) -> list[Device]: ...

    @abstractmethod
    def get_capabilities(self) -> Capabilities: ...

    @abstractmethod
    def reconcile(self, policies: list[Effective]): ...

    @abstractmethod
    def get_active_policies(self) -> list[Effective]: ...

    def get_device_status(self, device_id):
        return next((d for d in self.discover_devices() if d.id == device_id), None)

    def get_bandwidth_stats(self, device_id):
        return {"device_id": device_id, "download_mbps": None, "upload_mbps": None, "available": False}

    def set_bandwidth_limit(self, device_id, download_mbps=None, upload_mbps=None):
        device = self.get_device_status(device_id)
        if device is None:
            raise AdapterError("Unknown device")
        previous = self.get_active_policies()
        item = next((p for p in previous if p.device.id == device_id), Effective(device=device))
        item.download_mbps, item.upload_mbps = download_mbps, upload_mbps
        self.reconcile([p for p in previous if p.device.id != device_id] + [item])

    def remove_bandwidth_limit(self, device_id):
        self._remove(device_id, bandwidth=True)

    def block_device(self, device_id):
        device = self.get_device_status(device_id)
        if device is None:
            raise AdapterError("Unknown device")
        previous = self.get_active_policies()
        item = next((p for p in previous if p.device.id == device_id), Effective(device=device))
        item.blocked = True
        self.reconcile([p for p in previous if p.device.id != device_id] + [item])

    def unblock_device(self, device_id):
        self._remove(device_id, bandwidth=False)

    def _remove(self, device_id, bandwidth):
        updated = []
        for item in self.get_active_policies():
            if item.device.id == device_id:
                if bandwidth:
                    item.download_mbps, item.upload_mbps = None, None
                else:
                    item.blocked = False
            if item.blocked or item.download_mbps or item.upload_mbps:
                updated.append(item)
        self.reconcile(updated)


class ReadOnlyAdapter(RouterAdapter):
    def __init__(self, settings: Settings):
        self.settings = settings

    def get_capabilities(self):
        return Capabilities(
            adapter="readonly",
            mode=Mode.MONITOR,
            ipv6=True,
            reason="Passive neighbor cache only. No authorized traffic path is connected.",
        )

    def discover_devices(self):
        networks = [ipaddress.ip_network(n) for n in self.settings.authorized_cidrs]
        if not networks:
            return []
        own = {a.address.split("%")[0] for addresses in psutil.net_if_addrs().values() for a in addresses}
        grouped: dict[str, Device] = {}
        protected = {str(ipaddress.ip_address(address)) for address in self.settings.protected_addresses}
        for row in neighbors(self.settings.inventory_interface):
            try:
                address = ipaddress.ip_address(row.get("dst", "").split("%")[0])
                if not any(address.version == n.version and address in n for n in networks):
                    continue
                # iproute2 can omit "dev" when the command already filters by it.
                interface = row.get("dev") or self.settings.inventory_interface or ""
                if self.settings.inventory_interface and interface != self.settings.inventory_interface:
                    continue
                mac = row.get("lladdr")
                if not mac:
                    continue
                key = hashlib.sha256(f"{interface}:{mac.lower().replace('-', ':')}".encode()).hexdigest()[:20]
                raw_states = row.get("state", [])
                states = {
                    str(s).upper() for s in ([raw_states] if isinstance(raw_states, str) else raw_states)
                }
                device = grouped.setdefault(
                    key, Device(id=key, mac=mac, interface=interface, source="neighbor-cache")
                )
                if address not in device.addresses:
                    if len(device.addresses) >= 64:
                        # Preserve protection even if this identity has too many addresses to inventory.
                        device.protected |= str(address) in own or str(address) in protected
                        continue
                    device.addresses.append(address)
                if states & {"REACHABLE", "PERMANENT", "5", "6"}:
                    device.status = "online"
                    device.address_status[str(address)] = "online"
                else:
                    device.address_status[str(address)] = "unknown"
                device.protected |= str(address) in own or str(address) in protected
            except (ValueError, ValidationError):
                continue
        return list(grouped.values())

    def reconcile(self, policies):
        if policies:
            raise AdapterError("Monitor-only adapter cannot restrict traffic")

    def get_active_policies(self):
        return []


class MockAdapter(RouterAdapter):
    def __init__(self):
        self.policies: list[Effective] = []

    def get_capabilities(self):
        return Capabilities(
            adapter="mock",
            mode=Mode.DEMO,
            bandwidth=True,
            access=True,
            ipv6=True,
            simulated=True,
            reason="All devices and policy effects are simulated. No network changes.",
        )

    def discover_devices(self):
        return [
            Device(
                id=f"demo-{i}",
                nickname=name,
                mac=f"02:00:00:00:00:{i:02x}",
                addresses=[f"192.0.2.{i + 10}", f"2001:db8::{i}"],
                source="simulation",
                status="online",
                confirmed=True,
                simulated=True,
                protected=i == 1,
            )
            for i, name in enumerate(
                ["Management laptop", "Living room TV", "Gaming console", "Study tablet"], 1
            )
        ]

    def reconcile(self, policies):
        self.policies = [p.model_copy(deep=True) for p in policies]

    def get_active_policies(self):
        return [p.model_copy(deep=True) for p in self.policies]


class LinuxGatewayAdapter(RouterAdapter):
    lease_seconds = 90

    def __init__(self, settings: Settings):
        self.settings = settings
        context = ssl.create_default_context(cafile=settings.agent_ca_file)
        token = read_token(Path(settings.agent_token_file))
        self.client = httpx.Client(
            base_url=settings.agent_url,
            verify=context,
            timeout=15,
            trust_env=False,
            follow_redirects=False,
            headers={"Authorization": f"Bearer {token}"},
        )

    def _call(self, method, path, data=None):
        try:
            response = self.client.request(method, path, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 409:
                try:
                    detail = exc.response.json().get("detail")
                    if isinstance(detail, str):
                        raise AdapterError(f"Agent refused the snapshot: {detail[:500]}") from exc
                except (ValueError, AttributeError):
                    pass
            raise AdapterError(
                f"Agent returned HTTP {exc.response.status_code}; check its configuration and credential"
            ) from exc
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise AdapterError(
                f"Agent request failed ({type(exc).__name__}); inspect agent diagnostics"
            ) from exc

    def get_capabilities(self):
        try:
            return Capabilities.model_validate(self._call("GET", "/v1/capabilities"))
        except (AdapterError, ValidationError) as exc:
            return Capabilities(adapter="gateway", mode=Mode.MONITOR, reason=str(exc))

    def discover_devices(self):
        data = self._call("GET", "/v1/devices")
        if not isinstance(data, list):
            raise AdapterError("Agent returned invalid inventory")
        return [Device.model_validate(item) for item in data]

    def policy_target(self, device: Device) -> Device:
        addresses = [
            address
            for address in device.addresses
            if device.address_status.get(str(address)) == "online"
            and not (
                address.is_link_local or address.is_multicast or address.is_loopback or address.is_unspecified
            )
        ]
        return device.model_copy(
            update={
                "addresses": addresses,
                "address_status": {str(address): "online" for address in addresses},
            }
        )

    def reconcile(self, policies):
        snapshot = Snapshot(policies=policies, lease_seconds=self.lease_seconds)
        result = self._call("PUT", "/v1/policies", snapshot.model_dump(mode="json"))
        if not isinstance(result, dict) or result.get("installed") is not True:
            raise AdapterError("Agent did not acknowledge installed desired state")

    def get_active_policies(self):
        return [Effective.model_validate(item) for item in self._call("GET", "/v1/policies")]

    def close(self):
        self.client.close()


class LinuxBridgeAdapter(ReadOnlyAdapter):
    def get_capabilities(self):
        return Capabilities(
            adapter="bridge",
            mode=Mode.MONITOR,
            ipv6=True,
            reason="Inline bridge enforcement is not yet validated. Monitoring only; VLAN/offload support pending.",
        )


def make_adapter(settings):
    return {
        "readonly": ReadOnlyAdapter,
        "mock": lambda _: MockAdapter(),
        "gateway": LinuxGatewayAdapter,
        "bridge": LinuxBridgeAdapter,
    }[settings.adapter](settings)

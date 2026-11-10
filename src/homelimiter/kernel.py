"""Opt-in Linux gateway executor. Never used by the Windows controller."""

import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from pydantic import Field, field_validator, model_validator

from .adapters import AdapterError, ReadOnlyAdapter
from .config import Settings
from .models import Capabilities, Effective, Mode, Model, Snapshot

TABLE = "homelimiter"
ROOT = "1a10:"
IFB = "hlifb0"


class AgentConfig(Model):
    lan: str
    wan: str
    authorized_cidrs: list[str] = Field(min_length=1)
    protected_addresses: list[str] = Field(min_length=1)
    exclusive_interfaces: bool = False
    topology_authorized: bool = False
    link_mbps: int = Field(default=1000, ge=1, le=10000)

    @field_validator("lan", "wan")
    @classmethod
    def interface_name(cls, value):
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,15}", value) or value in {"lo", IFB}:
            raise ValueError("Use a physical/dedicated LAN or WAN interface name")
        return value

    @model_validator(mode="after")
    def valid_config(self):
        if self.lan == self.wan:
            raise ValueError("Routed mode needs separate LAN and WAN interfaces")
        for value in self.authorized_cidrs:
            network = ipaddress.ip_network(value, strict=True)
            if network.prefixlen < (8 if network.version == 4 else 16):
                raise ValueError("Authorized networks must be explicitly bounded")
        for value in self.protected_addresses:
            ipaddress.ip_address(value)
        return self


class CommandRunner:
    def run(self, argv: list[str], text: str | None = None):
        try:
            result = subprocess.run(argv, input=text, text=True, capture_output=True, timeout=15, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AdapterError(f"Command unavailable or timed out: {argv[0]}") from exc
        if result.returncode:
            raise AdapterError(f"{argv[0]} failed: {result.stderr.strip()[:400]}")
        return result.stdout

    def json(self, argv):
        return json.loads(self.run(argv) or "[]")


class LinuxEngine:
    def __init__(self, config: AgentConfig, root: Path, runner=None):
        self.config, self.root = config, root
        self.runner = runner or CommandRunner()
        self.lock = threading.RLock()
        root.mkdir(parents=True, exist_ok=True)
        self.journal = root / "owned-state.json"
        if self.journal.exists():
            state = json.loads(self.journal.read_text(encoding="utf-8"))
            if state["lan"] != config.lan or state["wan"] != config.wan:
                raise AdapterError(
                    "Recover resources with the original interface configuration before changing it"
                )
            self.owner = state["owner"]
        else:
            self.owner = uuid.uuid4().hex
        self.marker = "homelimiter:" + self.owner
        self.policies: list[Effective] = []
        self.deadline = 0.0
        self.last_error = None

    def _save_journal(self):
        path = self.root / "owned-state.tmp"
        path.write_text(
            json.dumps({"owner": self.owner, "lan": self.config.lan, "wan": self.config.wan}),
            encoding="utf-8",
        )
        path.replace(self.journal)

    def _table(self):
        tables = self.runner.json(["nft", "-j", "list", "tables"])
        entries = tables.get("nftables", [])
        if any(
            e.get("table", {}).get("family") == "inet" and e.get("table", {}).get("name") == TABLE
            for e in entries
        ):
            data = self.runner.json(["nft", "-j", "list", "table", "inet", TABLE])
            table = next(e["table"] for e in data["nftables"] if "table" in e)
            if not self.journal.exists() or table.get("comment") != self.marker:
                raise AdapterError("Refusing an nftables table not owned by this installation")
            return True
        return False

    def _qdiscs(self, device):
        return self.runner.json(["tc", "-j", "qdisc", "show", "dev", device])

    def _owned_root(self, device):
        return any(
            q.get("root") and q.get("handle") == ROOT and q.get("kind") == "htb" for q in self._qdiscs(device)
        )

    def _ifb_exists(self):
        links = self.runner.json(["ip", "-j", "-d", "link", "show"])
        link = next((row for row in links if row["ifname"] == IFB), None)
        if link and (
            not self.journal.exists()
            or link.get("ifalias") != self.marker
            or link.get("linkinfo", {}).get("info_kind") != "ifb"
        ):
            raise AdapterError("Refusing a pre-existing IFB not owned by HomeLimiter")
        return link is not None

    def preflight(self):
        if sys.platform != "linux" or os.geteuid() != 0:
            raise AdapterError("Enforcement requires a privileged Linux agent")
        if not self.config.topology_authorized or not self.config.exclusive_interfaces:
            raise AdapterError(
                "Explicit topology authorization and exclusive interface delegation are required"
            )
        if not all(shutil.which(tool) for tool in ("ip", "tc", "nft")):
            raise AdapterError("Install iproute2 and nftables")
        links = self.runner.json(["ip", "-j", "link", "show"])
        for name in (self.config.lan, self.config.wan):
            link = next((item for item in links if item["ifname"] == name), None)
            if link is None or "UP" not in link.get("flags", []) or link.get("master"):
                raise AdapterError(f"{name} must be up and routed, without a bridge/VRF master")
        families = {ipaddress.ip_network(n).version for n in self.config.authorized_cidrs}
        for version in families:
            path = (
                "/proc/sys/net/ipv4/ip_forward" if version == 4 else "/proc/sys/net/ipv6/conf/all/forwarding"
            )
            if Path(path).read_text().strip() != "1":
                raise AdapterError(
                    f"IPv{version} forwarding is not enabled; configure the gateway explicitly"
                )
            routes = self.runner.json(["ip", "-j", f"-{version}", "route", "show", "default"])
            if not routes or any(route.get("dev") != self.config.wan for route in routes):
                raise AdapterError(f"IPv{version} default route must exclusively use the configured WAN")
            rules = self.runner.json(["ip", "-j", f"-{version}", "rule", "show"])
            if any(
                rule.get("priority") not in {0, 32766, 32767}
                or rule.get("table") not in {"local", "main", "default"}
                or rule.get("src", "all") != "all"
                for rule in rules
            ):
                raise AdapterError(
                    "Policy routing requires additional path verification and is not supported"
                )
        self._table()
        self._ifb_exists()
        ruleset = self.runner.json(["nft", "-j", "list", "ruleset"])
        if any("flowtable" in entry for entry in ruleset.get("nftables", [])):
            raise AdapterError(
                "Flowtable offload may bypass forwarding policy; use a software-only managed path"
            )
        for qdisc in self._qdiscs(self.config.lan):
            handle, kind = qdisc.get("handle"), qdisc.get("kind")
            owned = self.journal.exists() and (
                (handle == ROOT and kind == "htb")
                or (handle == "ffff:" and kind == "ingress")
                or (qdisc.get("parent", "").startswith(ROOT) and kind == "fq_codel")
            )
            untouched_default = handle == "0:" and kind in {"noqueue", "pfifo_fast", "fq_codel"}
            if not owned and not untouched_default:
                raise AdapterError(
                    "LAN qdisc is not an unconfigured default or a journaled HomeLimiter resource"
                )

    def discover(self):
        adapter = ReadOnlyAdapter(
            Settings(
                authorized_cidrs=self.config.authorized_cidrs,
                protected_addresses=self.config.protected_addresses,
            )
        )
        return [device for device in adapter.discover_devices() if device.interface == self.config.lan]

    def validate_targets(self, policies):
        inventory = self.discover()
        local_addresses = {
            a["local"]
            for row in self.runner.json(["ip", "-j", "address", "show"])
            for a in row.get("addr_info", [])
        }
        protected = local_addresses | set(self.config.protected_addresses)
        cidrs = [ipaddress.ip_network(n) for n in self.config.authorized_cidrs]
        bindings = {}
        for observed in inventory:
            for address in observed.addresses:
                bindings.setdefault(str(address), []).append(observed)
        used = set()
        for item in policies:
            device = item.device
            if device.id in used:
                raise AdapterError("Duplicate device in snapshot")
            used.add(device.id)
            if (
                device.simulated
                or device.protected
                or not device.confirmed
                or not device.mac
                or not device.addresses
            ):
                raise AdapterError("Target must be real, confirmed and not protected")
            if device.interface != self.config.lan:
                raise AdapterError("Target is not on the managed LAN interface")
            for address in device.addresses:
                if (
                    str(address) in protected
                    or address.is_multicast
                    or address.is_loopback
                    or address.is_unspecified
                    or address.is_link_local
                ):
                    raise AdapterError("Protected or unsuitable target address")
                if not any(address.version == n.version and address in n for n in cidrs):
                    raise AdapterError("Target outside explicitly authorized networks")
                observed = bindings.get(str(address), [])
                if len(observed) != 1 or observed[0].mac != device.mac or observed[0].status != "online":
                    raise AdapterError("Target address has no fresh, unique matching neighbor binding")
                routes = self.runner.json(["ip", "-j", f"-{address.version}", "route", "get", str(address)])
                if not routes or routes[0].get("dev") != self.config.lan or routes[0].get("type") == "local":
                    raise AdapterError("Target routing does not use the managed LAN")
            for rate in (item.download_mbps, item.upload_mbps):
                if rate is not None and rate > self.config.link_mbps:
                    raise AdapterError("Device cap exceeds configured physical link speed")

    def firewall_script(self, policies, exists):
        lines = [f"delete table inet {TABLE}"] if exists else []
        lines += [
            f'add table inet {TABLE} {{ comment "{self.marker}"; }}',
            f"add chain inet {TABLE} forward {{ type filter hook forward priority -10; policy accept; }}",
        ]
        for item in policies:
            if not item.blocked:
                continue
            for address in item.device.addresses:
                family = "ip" if address.version == 4 else "ip6"
                for incoming, outgoing, direction in [
                    (self.config.lan, self.config.wan, "saddr"),
                    (self.config.wan, self.config.lan, "daddr"),
                ]:
                    lines.append(
                        f'add rule inet {TABLE} forward iifname "{incoming}" oifname "{outgoing}" {family} {direction} {address} counter drop'
                    )
        return "\n".join(lines) + "\n"

    def shaping_commands(self, policies):
        commands = []
        for interface, field, selector in [
            (self.config.lan, "download_mbps", "dst_ip"),
            (IFB, "upload_mbps", "src_ip"),
        ]:
            selected = [p for p in policies if getattr(p, field) is not None]
            if not selected:
                continue
            commands += [
                ["tc", "qdisc", "add", "dev", interface, "root", "handle", ROOT, "htb", "default", "1"],
                [
                    "tc",
                    "class",
                    "add",
                    "dev",
                    interface,
                    "parent",
                    ROOT,
                    "classid",
                    ROOT + "1",
                    "htb",
                    "rate",
                    f"{self.config.link_mbps}mbit",
                    "ceil",
                    f"{self.config.link_mbps}mbit",
                ],
            ]
            for index, item in enumerate(selected, 16):
                classid = ROOT + f"{index:x}"
                rate = f"{getattr(item, field):g}mbit"
                commands += [
                    [
                        "tc",
                        "class",
                        "add",
                        "dev",
                        interface,
                        "parent",
                        ROOT,
                        "classid",
                        classid,
                        "htb",
                        "rate",
                        rate,
                        "ceil",
                        rate,
                    ],
                    ["tc", "qdisc", "add", "dev", interface, "parent", classid, "fq_codel"],
                ]
                for address in item.device.addresses:
                    commands.append(
                        [
                            "tc",
                            "filter",
                            "add",
                            "dev",
                            interface,
                            "parent",
                            ROOT,
                            "protocol",
                            "ip" if address.version == 4 else "ipv6",
                            "pref",
                            str(index),
                            "flower",
                            "skip_hw",
                            selector,
                            str(address),
                            "classid",
                            classid,
                        ]
                    )
        return commands

    def _clear_shaping(self):
        ifb = self._ifb_exists()
        for qdisc in self._qdiscs(self.config.lan):
            if qdisc.get("handle") == ROOT and qdisc.get("kind") == "htb":
                if not self.journal.exists():
                    raise AdapterError("Unowned root qdisc")
                self.runner.run(["tc", "qdisc", "del", "dev", self.config.lan, "root", "handle", ROOT])
            if qdisc.get("handle") == "ffff:" and qdisc.get("kind") == "ingress":
                if not self.journal.exists():
                    raise AdapterError("Unowned ingress qdisc")
                self.runner.run(["tc", "qdisc", "del", "dev", self.config.lan, "ingress"])
        if ifb:
            self.runner.run(["ip", "link", "del", "dev", IFB])

    def _install(self, policies):
        exists = self._table()
        script = self.firewall_script(policies, exists)
        if policies:
            self.runner.run(["nft", "-c", "-f", "-"], script)
        self._clear_shaping()
        if any(p.upload_mbps is not None for p in policies):
            self.runner.run(["ip", "link", "add", "name", IFB, "type", "ifb"])
            self.runner.run(["ip", "link", "set", "dev", IFB, "alias", self.marker])
            self.runner.run(["ip", "link", "set", "dev", IFB, "up"])
            self.runner.run(["tc", "qdisc", "add", "dev", self.config.lan, "handle", "ffff:", "ingress"])
            self.runner.run(
                [
                    "tc",
                    "filter",
                    "add",
                    "dev",
                    self.config.lan,
                    "parent",
                    "ffff:",
                    "protocol",
                    "all",
                    "pref",
                    "1",
                    "matchall",
                    "action",
                    "mirred",
                    "egress",
                    "redirect",
                    "dev",
                    IFB,
                ]
            )
        for command in self.shaping_commands(policies):
            self.runner.run(command)
        if policies:
            self.runner.run(["nft", "-f", "-"], script)
        elif exists:
            self.runner.run(["nft", "delete", "table", "inet", TABLE])
        if policies and not self._table():
            raise AdapterError("Firewall table installation could not be verified")
        for interface, field in [(self.config.lan, "download_mbps"), (IFB, "upload_mbps")]:
            if any(getattr(p, field) is not None for p in policies) and not self._owned_root(interface):
                raise AdapterError("Shaper installation could not be verified")

    def apply(self, snapshot: Snapshot):
        with self.lock:
            if not snapshot.policies:
                self.recover()
                return {"installed": True, "traffic_verified": False, "lease_seconds": 0}
            self.preflight()
            self.validate_targets(snapshot.policies)
            previous = [p.model_copy(deep=True) for p in self.policies]
            old_key = hashlib.sha256(
                json.dumps(
                    [p.model_dump(mode="json", exclude={"device": {"last_seen"}}) for p in previous],
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            new_key = hashlib.sha256(
                json.dumps(
                    [p.model_dump(mode="json", exclude={"device": {"last_seen"}}) for p in snapshot.policies],
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            self._save_journal()
            if old_key != new_key or not self._installed(snapshot.policies):
                try:
                    self._install(snapshot.policies)
                except Exception as exc:
                    try:
                        self._install(previous)
                    except Exception as rollback:
                        self.last_error = f"Apply failed: {exc}; rollback failed: {rollback}"
                        raise AdapterError(self.last_error) from exc
                    self.last_error = f"Apply failed; previous owned snapshot restored: {exc}"
                    raise AdapterError(self.last_error) from exc
            self.policies = [p.model_copy(deep=True) for p in snapshot.policies]
            self.deadline = time.monotonic() + snapshot.lease_seconds
            self.last_error = None
            return {"installed": True, "traffic_verified": False, "lease_seconds": snapshot.lease_seconds}

    def _installed(self, policies):
        if not policies:
            return not self._table() and not self._owned_root(self.config.lan) and not self._ifb_exists()
        if not self._table():
            return False
        for interface, field in [(self.config.lan, "download_mbps"), (IFB, "upload_mbps")]:
            selected = [p for p in policies if getattr(p, field) is not None]
            if selected:
                if interface == IFB and not self._ifb_exists():
                    return False
                if not self._owned_root(interface):
                    return False
                classes = self.runner.json(["tc", "-j", "class", "show", "dev", interface])
                if len([c for c in classes if c.get("handle", "").startswith(ROOT)]) != len(selected) + 1:
                    return False
        return True

    def recover(self):
        """Remove journal-owned resources on restart; never replay stale restrictions."""
        with self.lock:
            self._table()
            self._clear_shaping()
            if self._table():
                self.runner.run(["nft", "delete", "table", "inet", TABLE])
            self.policies = []
            self.deadline = 0

    def watchdog(self):
        with self.lock:
            if self.deadline and time.monotonic() >= self.deadline:
                self.recover()
                return True
            return False

    def capabilities(self):
        try:
            self.preflight()
            return Capabilities(
                adapter="gateway",
                mode=Mode.PARTIAL,
                bandwidth=True,
                access=True,
                ipv6=True,
                reason="Experimental routed agent; topology checks pass. Installed rules are checked, actual traffic coverage is not certified.",
            )
        except (AdapterError, OSError, ValueError) as exc:
            return Capabilities(adapter="gateway", mode=Mode.MONITOR, reason=str(exc))

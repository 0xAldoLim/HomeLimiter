"""Invoked only inside the disposable gateway namespace by test_network.py."""

import json
import subprocess
import sys
from pathlib import Path

from homelimiter.kernel import AgentConfig, LinuxEngine
from homelimiter.models import Effective, Snapshot


def main():
    client, root = sys.argv[1:]
    if not client.startswith("hltest-"):
        raise RuntimeError("This scenario is restricted to disposable test namespaces")

    def probe(*args):
        return subprocess.run(
            ["ip", "netns", "exec", client, *args], capture_output=True, text=True, timeout=30
        )

    for address in ("198.51.100.2", "2001:db8:2::2"):
        baseline = probe("ping", "-c", "2", "-W", "2", address)
        assert baseline.returncode == 0, json.dumps(
            {
                "target": address,
                "stdout": baseline.stdout,
                "stderr": baseline.stderr,
                "gateway_addresses": subprocess.run(
                    ["ip", "-j", "address"], capture_output=True, text=True
                ).stdout,
                "gateway_ipv6_routes": subprocess.run(
                    ["ip", "-j", "-6", "route"], capture_output=True, text=True
                ).stdout,
                "client_ipv6_addresses": probe("ip", "-j", "-6", "address").stdout,
                "client_ipv6_routes": probe("ip", "-j", "-6", "route").stdout,
            }
        )
    config = AgentConfig(
        lan="lan0",
        wan="wan0",
        authorized_cidrs=["192.0.2.0/24", "2001:db8:1::/64"],
        protected_addresses=["192.0.2.254"],
        exclusive_interfaces=True,
        topology_authorized=True,
    )
    engine = LinuxEngine(config, Path(root))
    engine.runner.run(["nft", "add", "table", "inet", "test_guard"])
    target = next(d for d in engine.discover() if "192.0.2.2" in [str(a) for a in d.addresses])
    # Pin bindings only inside this disposable fixture. Avoid NUD DELAY/STALE timer
    # transitions interfering with rate measurements; production requires fresh bindings.
    for address in target.addresses:
        engine.runner.run(
            [
                "ip",
                f"-{address.version}",
                "neigh",
                "replace",
                str(address),
                "lladdr",
                target.mac,
                "nud",
                "permanent",
                "dev",
                "lan0",
            ]
        )
    target = next(d for d in engine.discover() if d.id == target.id)
    target.confirmed = True
    policy = Effective(device=target, download_mbps=2, upload_mbps=2)
    engine.apply(Snapshot(policies=[policy]))
    # An identical update must renew the lease without duplicating resources.
    engine.apply(Snapshot(policies=[policy]))
    rates = []
    for address in ("198.51.100.2", "2001:db8:2::2"):
        for reverse in (False, True):
            args = ["iperf3", "-c", address, "-t", "5", "-O", "1", "-J"] + (["-R"] if reverse else [])
            result = probe(*args)
            assert result.returncode == 0, result.stderr + result.stdout
            data = json.loads(result.stdout)
            rates.append(data["end"]["sum_received"]["bits_per_second"] / 1_000_000)
    # Renew live bindings before the disruptive isolated pause.
    for address in ("198.51.100.2", "2001:db8:2::2"):
        assert probe("ping", "-c", "1", "-W", "2", address).returncode == 0
    policy.blocked = True
    engine.apply(Snapshot(policies=[policy]))
    blocked4 = probe("ping", "-c", "1", "-W", "1", "198.51.100.2").returncode != 0
    blocked6 = probe("ping", "-c", "1", "-W", "1", "2001:db8:2::2").returncode != 0
    engine.recover()
    assert probe("ping", "-c", "1", "-W", "2", "198.51.100.2").returncode == 0
    guard = engine.runner.json(["nft", "-j", "list", "table", "inet", "test_guard"])
    assert not engine._table() and not engine._ifb_exists()
    print(
        json.dumps(
            {
                "ipv4_blocked": blocked4,
                "ipv6_blocked": blocked6,
                "measured_mbps": rates,
                "unrelated_table_preserved": bool(guard),
            }
        )
    )


if __name__ == "__main__":
    main()

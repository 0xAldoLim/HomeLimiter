"""All links and sysctls live inside disposable named namespaces, never the host path."""

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        sys.platform != "linux" or os.environ.get("HOMELIMITER_NET_TESTS") != "1",
        reason="Requires Linux root and HOMELIMITER_NET_TESTS=1; no live home network is used",
    ),
]


def test_disposable_dual_stack_gateway(tmp_path):
    if os.geteuid() != 0:
        pytest.fail("Opt-in namespace tests require root")
    for tool in ("ip", "tc", "nft", "iperf3", "ping"):
        assert shutil.which(tool), f"Install {tool} before opting in"
    prefix = "hltest-" + uuid.uuid4().hex[:8]
    client, gateway, server = [prefix + suffix for suffix in ("c", "g", "s")]
    created = []
    iperf = None

    def run(*args):
        result = subprocess.run(args, check=False, text=True, capture_output=True, timeout=90)
        assert result.returncode == 0, f"{args}\n{result.stdout}\n{result.stderr}"
        return result

    def ip(ns, *args):
        return run("ip", "-n", ns, *args)

    try:
        for ns in (client, gateway, server):
            run("ip", "netns", "add", ns)
            created.append(ns)
            ip(ns, "link", "set", "lo", "up")
        ip(gateway, "link", "add", "lan0", "type", "veth", "peer", "name", "eth0", "netns", client)
        ip(gateway, "link", "add", "wan0", "type", "veth", "peer", "name", "eth0", "netns", server)
        for ns, interface, ipv4, ipv6 in [
            (client, "eth0", "192.0.2.2/24", "2001:db8:1::2/64"),
            (gateway, "lan0", "192.0.2.1/24", "2001:db8:1::1/64"),
            (gateway, "wan0", "198.51.100.1/24", "2001:db8:2::1/64"),
            (server, "eth0", "198.51.100.2/24", "2001:db8:2::2/64"),
        ]:
            ip(ns, "address", "add", ipv4, "dev", interface)
            ip(ns, "-6", "address", "add", ipv6, "dev", interface, "nodad")
            ip(ns, "link", "set", interface, "up")
        for ns, ipv4, ipv6 in [
            (client, "192.0.2.1", "2001:db8:1::1"),
            (gateway, "198.51.100.2", "2001:db8:2::2"),
            (server, "198.51.100.1", "2001:db8:2::1"),
        ]:
            ip(ns, "route", "add", "default", "via", ipv4)
            ip(ns, "-6", "route", "add", "default", "via", ipv6)
        run(
            "ip",
            "netns",
            "exec",
            gateway,
            "sysctl",
            "-w",
            "net.ipv4.ip_forward=1",
            "net.ipv6.conf.all.forwarding=1",
        )
        iperf = subprocess.Popen(
            ["ip", "netns", "exec", server, "iperf3", "-s"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        scenario = Path(__file__).with_name("netns_scenario.py")
        result = run("ip", "netns", "exec", gateway, sys.executable, str(scenario), client, str(tmp_path))
        report = json.loads(result.stdout)
        assert report["ipv4_blocked"] and report["ipv6_blocked"]
        for rate in report["measured_mbps"]:
            assert 0.3 < rate < 3.5, report
        assert report["unrelated_table_preserved"]
        print(json.dumps(report))
    finally:
        if iperf:
            iperf.terminate()
            iperf.wait(timeout=10)
        for ns in reversed(created):
            assert ns.startswith(prefix) and len(prefix) > 10
            subprocess.run(["ip", "netns", "delete", ns], check=False, capture_output=True)

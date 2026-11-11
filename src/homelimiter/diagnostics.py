import ctypes
import ipaddress
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import psutil


def run_read(args: list[str], accepted=(0,)):
    try:
        proc = subprocess.run(args, capture_output=True, encoding="utf-8", errors="replace", timeout=8)
        return proc.stdout if proc.returncode in accepted else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def powershell(script: str):
    return run_read(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.Encoding]::UTF8; " + script,
        ]
    )


def parse(raw, fallback):
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return fallback


def local_networks(values):
    networks = set()
    for value in values:
        if value.family not in {socket.AF_INET, socket.AF_INET6} or not value.netmask:
            continue
        try:
            address = ipaddress.ip_address(value.address.split("%")[0])
            if address.is_loopback or address.is_link_local or address.is_unspecified:
                continue
            mask = f"{int(ipaddress.ip_address(value.netmask.split('%')[0])):0{address.max_prefixlen}b}"
            if "01" not in mask:
                networks.add(str(ipaddress.ip_network(f"{address}/{mask.count('1')}", strict=False)))
        except ValueError:
            continue
    return sorted(networks)


def diagnose():
    addresses = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    windows = os.name == "nt"
    linux = sys.platform == "linux"
    interfaces = {
        name: [{"family": str(a.family), "address": a.address, "netmask": a.netmask} for a in values]
        for name, values in addresses.items()
    }
    forwarding = {}
    indexes = {}
    if linux:
        routes = parse(run_read(["ip", "-j", "route", "show", "default"]), [])
        routes6 = parse(run_read(["ip", "-j", "-6", "route", "show", "default"]), [])
        virtualization = run_read(["systemd-detect-virt"], accepted=(0, 1)).strip() or "unknown"
        for family, name in {
            "ipv4": "/proc/sys/net/ipv4/ip_forward",
            "ipv6": "/proc/sys/net/ipv6/conf/all/forwarding",
        }.items():
            try:
                forwarding[family] = Path(name).read_text().strip() == "1"
            except OSError:
                forwarding[family] = False
    elif windows:
        data = parse(
            powershell(
                "$n = @(Get-NetIPInterface | Select-Object InterfaceIndex,InterfaceAlias); "
                "$r = @(Get-NetRoute | Where-Object { $_.DestinationPrefix -in '0.0.0.0/0','::/0' } "
                "| Sort-Object RouteMetric | Select-Object InterfaceIndex,InterfaceAlias,NextHop,DestinationPrefix); "
                "$c = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue; "
                "@{Interfaces=$n; Routes=$r; Model=$c.Model; Maker=$c.Manufacturer} | ConvertTo-Json -Compress"
            ),
            {},
        )
        indexes = {item["InterfaceAlias"]: str(item["InterfaceIndex"]) for item in data.get("Interfaces", [])}
        virtualization = " ".join(filter(None, [data.get("Maker"), data.get("Model")])) or "unknown"
        routes, routes6 = [], []
        for item in data.get("Routes", []):
            target = routes if item["DestinationPrefix"] == "0.0.0.0/0" else routes6
            target.append({"dev": item["InterfaceAlias"], "gateway": item["NextHop"]})
    else:
        routes, routes6, virtualization = [], [], "unknown"
    names = sorted(set(addresses) | set(indexes))
    return {
        "os": platform.system(),
        "release": platform.release(),
        "python": platform.python_version(),
        "administrator": bool(ctypes.windll.shell32.IsUserAnAdmin()) if windows else os.geteuid() == 0,
        "interfaces": interfaces,
        "interface_choices": [
            {
                "name": name,
                "id": indexes.get(name, name),
                "up": bool(name in stats and stats[name].isup),
                "networks": local_networks(addresses.get(name, [])),
            }
            for name in names
            if not windows or name in indexes
        ],
        "default_routes_ipv4": routes,
        "default_routes_ipv6": routes6,
        "virtualization": virtualization,
        "forwarding": forwarding,
        "tools": {tool: bool(shutil.which(tool)) for tool in ("ip", "tc", "nft", "iperf3")},
        "note": "Diagnostics do not establish that other devices traverse this host.",
    }


def neighbors(interface: str | None = None):
    if sys.platform == "linux":
        args = ["ip", "-j", "neigh", "show"] + (["dev", interface] if interface else [])
        rows = parse(run_read(args), None)
        if not isinstance(rows, list):
            raise RuntimeError(
                "Cannot read the neighbor cache. Check the selected interface and install iproute2."
            )
        return rows
    if os.name == "nt":
        data = parse(
            powershell(
                "ConvertTo-Json -Compress -InputObject @(Get-NetNeighbor | "
                "Select-Object IPAddress,LinkLayerAddress,InterfaceIndex,State)"
            ),
            None,
        )
        if not isinstance(data, list):
            raise RuntimeError(
                "Cannot read the Windows neighbor cache. Check that Get-NetNeighbor is available."
            )
        return [
            {
                "dst": row["IPAddress"],
                "lladdr": row["LinkLayerAddress"],
                "dev": str(row["InterfaceIndex"]),
                "state": [str(row["State"])],
            }
            for row in data
            if not interface or str(row["InterfaceIndex"]) == interface
        ]
    return []

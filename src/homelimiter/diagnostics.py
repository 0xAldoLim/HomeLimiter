import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import psutil


def run_read(args: list[str]):
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=8, check=False)
        return proc.stdout if proc.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def diagnose():
    interfaces = {
        name: [{"family": str(a.family), "address": a.address, "netmask": a.netmask} for a in values]
        for name, values in psutil.net_if_addrs().items()
    }
    linux = sys.platform == "linux"
    if linux:
        routes = run_read(["ip", "-j", "route", "show", "default"])
        routes6 = run_read(["ip", "-j", "-6", "route", "show", "default"])
        virtualization = run_read(["systemd-detect-virt"]).strip() or "unknown"
    elif os.name == "nt":
        routes = run_read(["route", "print", "0.0.0.0"])
        routes6 = run_read(["route", "print", "::/0"])
        virtualization = "unknown (VMware mode does not prove traffic control)"
    else:
        routes, routes6, virtualization = "", "", "unknown"
    forwarding = {}
    if linux:
        for family, file in {
            "ipv4": "/proc/sys/net/ipv4/ip_forward",
            "ipv6": "/proc/sys/net/ipv6/conf/all/forwarding",
        }.items():
            forwarding[family] = Path(file).read_text().strip() == "1" if Path(file).exists() else False
    return {
        "os": platform.system(),
        "release": platform.release(),
        "python": platform.python_version(),
        "administrator": os.geteuid() == 0
        if linux
        else bool(ctypes.windll.shell32.IsUserAnAdmin())
        if os.name == "nt"
        else False,
        "interfaces": interfaces,
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
        try:
            return json.loads(run_read(args) or "[]")
        except json.JSONDecodeError:
            return []
    if os.name == "nt":
        script = "Get-NetNeighbor | Select-Object IPAddress,LinkLayerAddress,InterfaceIndex,State | ConvertTo-Json -Compress"
        try:
            data = json.loads(
                run_read(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script]) or "[]"
            )
        except json.JSONDecodeError:
            return []
        return [
            {
                "dst": row["IPAddress"],
                "lladdr": row["LinkLayerAddress"],
                "dev": str(row["InterfaceIndex"]),
                "state": [str(row["State"])],
            }
            for row in (data if isinstance(data, list) else [data])
        ]
    return []

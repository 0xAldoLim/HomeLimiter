# HomeLimiter

Router-agnostic network management through an **authorized traffic path**.
Windows and Linux controller; separate Linux gateway agent. No spoofing,
interception, router reconfiguration, telemetry, or hidden installation.

HomeLimiter 0.1 is an initial implementation, not a production-certified network appliance.
The default is **MONITOR ONLY**. Demo policies are explicitly simulated.
A Windows PC or a bridged/NAT Kali VM cannot control other household devices merely by sharing their network.

## Implemented

- Passive IPv4/IPv6 neighbor inventory within explicitly authorized ranges, persistent
  nicknames, identity confirmation, collision detection, and protected devices.
- Authenticated local API and responsive dashboard: overview, devices/details,
  bandwidth, access, scheduling, agents, diagnostics, audit logs and settings.
- Separate upload/download caps, internet pauses, expiry, weekly overnight windows,
  timezone/DST handling, conflict resolution and restart reconciliation.
- Typer CLI with exact targets, confirmations, dry runs and emergency restoration.
- Experimental Linux routed agent using owned nftables tables, HTB/fq_codel and IFB,
  verified TLS or loopback SSH transport, rollback and a controller-loss lease watchdog.
- Windows/Linux installers, dependency lock/audit and isolated namespace/browser CI.

Inline bridge enforcement, live throughput counters, DHCP/router integrations, and
automated proof of full traffic coverage remain future work. See the
[capability matrix](docs/SUPPORTED_CAPABILITIES.md) and [roadmap](docs/ROADMAP.md).

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\homelimiter init
.venv\Scripts\homelimiter dashboard
```

Open http://127.0.0.1:8787 and paste the local admin token from `homelimiter token`.
Use `homelimiter --demo dashboard` for a separate, simulated inventory.
See [installation](docs/INSTALLATION.md), [capabilities](docs/SUPPORTED_CAPABILITIES.md),
[architecture](docs/ARCHITECTURE.md), [security](SECURITY.md), and [research](docs/RESEARCH.md).

## Development

```sh
python -m pip install -e '.[dev]'
python -m pytest
python -m ruff check src tests
```

The dashboard uses accessible HTML, CSS, and JavaScript modules served by FastAPI.
No Node toolchain or Docker is required. See [contributing](CONTRIBUTING.md).

The UI follows [Hallmark's Console material](https://github.com/Nutlope/hallmark) with
local fonts, paper/graphite modes and a device ledger. See the shared [design system](design.md)
and [redesign record](docs/UI_REDESIGN.md).

The [testing guide](docs/TESTING.md) describes opt-in real browser and dual-stack
namespace tests. Never run disruptive validation against a live household network.

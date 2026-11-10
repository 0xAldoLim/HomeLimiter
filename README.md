# HomeLimiter

Router-agnostic network management through an **authorized traffic path**.
Windows and Linux controller; separate Linux gateway agent. No spoofing,
interception, router reconfiguration, telemetry, or hidden installation.

HomeLimiter 0.1 is an initial implementation, not a production-certified network appliance.
The default is **MONITOR ONLY**. Demo policies are explicitly simulated.
A Windows PC or a bridged/NAT Kali VM cannot control other household devices merely by sharing their network.

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

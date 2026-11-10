# Installation

Requirements: Python 3.12+ and pip. No Docker, Node, router API or VMware is required
for the controller. Development needs the optional `.[dev]` dependencies.

```sh
git clone git@github.com:0xAldoLim/HomeLimiter.git
cd HomeLimiter
python -m venv .venv
# Windows:
.venv\Scripts\python -m pip install -e .
.venv\Scripts\homelimiter init
.venv\Scripts\homelimiter token
.venv\Scripts\homelimiter dashboard
# Linux:
.venv/bin/python -m pip install -e .
.venv/bin/homelimiter init
.venv/bin/homelimiter token
.venv/bin/homelimiter dashboard
```

Open http://127.0.0.1:8787, paste the credential, and review the mode indicator.
`--demo` before the command uses a separate state subdirectory and simulated devices.
Do not share or commit tokens. The UI keeps the token in memory; reload requires login.

Default state: `%LOCALAPPDATA%\HomeLimiter` on Windows or `~/.local/share/HomeLimiter`
on Linux. Override with `HOMELIMITER_HOME` or `homelimiter --home PATH ...`.
Config is `config.json` in that directory. Use `config/controller.example.json` as a
reference. Add only authorized IPv4/IPv6 CIDRs, then restart and refresh inventory.
Neighbor caches are incomplete, and no active scan is performed. Review MAC/addresses
on the device details page before confirming identity. Nicknames and exclusions persist.

The dashboard process runs the persistent scheduler. Run one process per state directory;
offline CLI commands refuse access while it is running. Use the dashboard/API to manage
the running service, or stop it before using CLI mutations. A CLI restriction renews a
remote agent lease once; start the dashboard within the 90-second lease for sustained
enforcement. Without the controller, the running agent restores traffic after expiry.

## CLI examples

```sh
homelimiter doctor
homelimiter --demo devices
homelimiter --demo limit demo-2 --download 2 --upload 1 --dry-run
homelimiter --demo limit demo-2 --download 2 --upload 1 --minutes 30 --yes
homelimiter --demo pause demo-3 --minutes 15 --yes
homelimiter --demo schedules
homelimiter --demo schedule-add config/schedule.example.json --dry-run
homelimiter --demo resume demo-2
homelimiter --demo logs
homelimiter --demo emergency-restore --yes
```

Replace the example schedule's target ID before use. `resume` removes every policy for
the device, including future schedules; `remove POLICY_ID` removes a single policy.
Use `identify DEVICE_ID --yes --nickname NAME` only after checking its real identity.

## Reproducibility

`requirements-dev.lock` records the exact packages audited in the Windows development
environment, excluding the editable project itself. It is not a hash-verified multi-OS
lock. For replay, create a venv, install `-r requirements-dev.lock`, then `-e . --no-deps`.
For normal installs pip resolves the compatible ranges in pyproject.toml.

Build a wheel with `python -m build`; static assets are packaged inside the wheel.
Upgrades retain the state directory. Back up config and SQLite while the controller is
stopped. No daemon, firewall policy, scheduled task, or system service is installed by
the bootstrap scripts.

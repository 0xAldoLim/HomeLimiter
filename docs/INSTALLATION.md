# Installation and operation

Install Git and Python 3.12 or later. On Linux, install venv support for that interpreter.
From the repository run `./run.sh` on Linux or `.un.ps1` in Windows PowerShell. The
launcher creates a local `.venv` and installs declared dependencies on first run or
when package metadata changes. No service or system networking configuration is installed.
Use `HOMELIMITER_PYTHON` to select a full Python executable path for a new venv.

Without the launcher, create a local venv using `python -m venv .venv`, then use
`..venvScriptspython.exe -m pip install -e .` on Windows or
`.venv/bin/python -m pip install -e .` on Linux. Run the installed `homelimiter`
entry point in that venv. No activation is required when you call the full path.

## Profiles and configuration

State defaults to `%LOCALAPPDATA%HomeLimiter` on Windows and
`~/.local/share/HomeLimiter` on Linux. Set `HOMELIMITER_HOME` or put `--home PATH`
before the command. `--demo` uses the `demo` subdirectory and never connects to an
agent. If you choose Demo in the wizard, reopen it with `--demo`.

Run the wizard under **4 Network → Setup wizard**. For monitoring, select an interface
or all interfaces in explicitly approved CIDRs. Blank CIDRs disable discovery.
A neighbor cache is incomplete; refresh after devices communicate naturally and
verify the MAC and addresses before confirming. To connect to an existing agent, supply
its origin, private token file and trusted CA as appropriate.

Existing v0.1 state and policy IDs are reused. Back up private config and SQLite state
while the controller is stopped before upgrading. Existing nondefault configurations
are kept, and setup can be rerun. If configuration cannot load, use `homelimiter check`
to identify the problem and repair the private `config.json` using
[the example](../config/controller.example.json). Restore existing restrictions before
changing the configured adapter or network scope.

## Keep schedules running

In a normal local terminal session, the scheduler checks inventory and policies about
every 15 seconds while the process is open. Graceful exit requests removal of its live
rules, retaining saved policies. A running agent restores after the lease expires if
the controller disappears unexpectedly.

For schedules that should continue when the TUI closes:

```powershell
# Windows, first terminal:
.\run.ps1 serve
# Windows, second terminal:
.\run.ps1 --connect 8787
```

```bash
# Linux, first terminal:
./run.sh serve
# Linux, second terminal:
./run.sh --connect 8787
```

Use the same `--home` and `--demo` options in both commands. If 8787 is occupied,
use `serve --port PORT` and `--connect PORT`. The API binds to literal loopback,
and the client reads the profile's private admin credential automatically.
One controller owns each state directory. Stop it before using local setup or offline
mutations. `--connect PORT` also works with CLI commands such as `status` and `logs`.
Closing a connected TUI does not affect the scheduler. Stop the headless process to stop
renewing leases. No persistent OS service is registered.

After restart, HomeLimiter evaluates the current time and fresh inventory. Missed events
are not replayed, and expired rules are excluded. Standalone CLI mutations reconcile once;
the agent's normal lease expires unless a running controller renews it. If the agent itself
dies abruptly, restart or [recover it](LINUX_SETUP.md#recovery) using the original state.

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

Replace the schedule's target ID before using it outside the demo. `resume` removes
all rules for the device, including future schedules; `remove POLICY_ID` removes one.
`emergency-restore` clears saved policies and requests removal of owned rules, reporting
an error if agent restoration cannot be confirmed.

## Packaging

`requirements-dev.lock` records the audited Windows development resolution. It is not
a hash-verified cross-platform lock. For replay, install that file and then install
`-e . --no-deps` in a new venv. The normal launcher uses the supported dependency ranges
in `pyproject.toml`. Build the sdist and wheel with `python -m build`.
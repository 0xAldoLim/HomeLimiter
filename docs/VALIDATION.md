# Validation record

Validated on 2026-11-10. Code commit:
`31da725723cdda78c10579dc53c1ace2cf59780d`.

[GitHub Actions run](https://github.com/0xAldoLim/HomeLimiter/actions/runs/42741187914)
completed successfully in all six jobs:

| Job | Result |
|---|---|
| Controller, Windows, Python 3.12 | Passed: unit/protocol/security tests, lint, format, package build |
| Controller, Windows, Python 3.14 | Passed: unit/protocol/security tests, lint, format, package build |
| Controller, Ubuntu, Python 3.12 | Passed: unit/protocol/security tests, lint, format, package build |
| Controller, Ubuntu, Python 3.14 | Passed: unit/protocol/security tests, lint, format, package build |
| Chromium browser on Ubuntu | Passed: authenticated demo, navigation, policies, schedules, safe text rendering, themes and mobile layout |
| Disposable Linux gateway namespaces | Passed: actual dual-stack shaping, access pause/restoration, idempotence and unrelated-table preservation |

The isolated gateway fixture pinned its dynamically observed MAC/IP bindings as permanent
inside the test namespace to avoid NUD timer transitions during measurements. The
production agent retains strict per-address reachability checks. Initial test failures
exposed a dual-stack tc priority collision; the fix uses separate IPv4/IPv6 priorities.

## Actual traffic measurements

Configured upload and download caps: **2 Mbps**. iperf3 receiver throughput:

| Protocol/direction | Measured Mbps |
|---|---:|
| IPv4 upload | 1.8864 |
| IPv4 download | 1.8874 |
| IPv6 upload | 1.8864 |
| IPv6 download | 1.8875 |

IPv4 and IPv6 ping were blocked by the pause and restored after recovery. An unrelated
`inet test_guard` table survived. All links, routes, forwarding sysctls, firewall rules
and qdiscs for this test were confined to three disposable namespaces on the CI runner.
No household network or physical gateway was modified or certified.

## Local validation and limits

- Windows Python 3.14: full available suite including Chrome; Linux namespace test is
  skipped locally because this host has no usable WSL/Linux networking environment.
- Dependency lock audited with `pip-audit`: no known vulnerabilities reported at audit time.
- `pip check` passed; sdist/wheel builds succeeded; installed wheel contains the HTML,
  CSS and JavaScript dashboard assets.
- PowerShell bootstrap parser and Bash installer syntax checks passed. A clean Linux
  machine bootstrap, physical gateway deployment, TLS certificate provisioning and
  inline bridge enforcement were not performed on the user's devices.
- Unit tests cover scheduling/expiry/restart, policy conflicts, uncertain identities,
  authentication/origin/body limits, agent transport, ownership, lease expiry and
  injected apply/rollback failures. The namespace test exercises actual networking;
  it does not replace physical topology validation.

Agent mode remains **PARTIAL CONTROL** for the experimental routed backend. This record
does not justify reporting FULL CONTROL over an arbitrary real household device.

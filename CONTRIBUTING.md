# Contributing

Use Python 3.12+ and an isolated venv. Install `.[dev]`, run `pytest`, `ruff check src tests`,
and `ruff format --check src tests`. Add behavioral tests for policy/security changes.
No tests may touch a live network. Network namespace tests require explicit opt-in.

Keep capability claims accurate. Do not introduce spoofing, global firewall flushes,
shell-constructed network commands, telemetry, or secrets. Document licensing for any
copied code; original implementation is preferred. Keep admin actions confirmable and
audit failures as well as successes. Submit focused conventional commits.

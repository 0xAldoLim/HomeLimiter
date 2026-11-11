#!/usr/bin/env bash
set -euo pipefail

fail() { printf 'HomeLimiter: %s\n' "$1" >&2; exit 1; }
[[ "$(uname -s)" == Linux ]] || fail "This launcher is for Linux. On Windows, run .\\run.ps1."
cd -- "$(dirname -- "$0")"

supports_python() {
    "$1" -c 'import sys; sys.exit(not (sys.version_info.major == 3 and sys.version_info.minor >= 12))' >/dev/null 2>&1
}

if [[ ! -x .venv/bin/python ]]; then
    [[ ! -e .venv ]] || fail "This .venv is incomplete or belongs to another OS. Rename it and rerun ./run.sh."
    python_command="$(command -v python3 || true)"
    if [[ -v HOMELIMITER_PYTHON ]]; then
        python_command="$HOMELIMITER_PYTHON"
    fi
    supports_python "$python_command" ||
        fail "Install Python 3.12+ and its venv package, or set HOMELIMITER_PYTHON to a suitable interpreter."
    "$python_command" -m venv .venv ||
        fail "Could not create .venv. Install the venv package for this Python (python3-venv on Debian/Kali), rename the incomplete .venv, then retry."
fi

supports_python .venv/bin/python ||
    fail "The local .venv needs a working Python 3.12+. Rename .venv and rerun ./run.sh."
.venv/bin/python scripts/prepare.py
exec .venv/bin/python -m homelimiter.cli "$@"
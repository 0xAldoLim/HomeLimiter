#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$project_root"
python3 -c 'import sys; assert sys.version_info >= (3, 12), "Python 3.12+ required"'
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/homelimiter init
printf '%s\n' 'Controller installed in .venv. No networking was modified.' \
  'Read credential: .venv/bin/homelimiter token' \
  'Launch: .venv/bin/homelimiter dashboard'

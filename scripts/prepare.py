"""Install the editable app in the launcher's venv only when needed."""

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path


def main():
    if sys.prefix == sys.base_prefix:
        print("HomeLimiter: run the launcher so dependencies stay in a virtual environment.", file=sys.stderr)
        return 1
    project = Path(__file__).resolve().parents[1]
    stamp = Path(sys.prefix) / ".homelimiter-install"
    try:
        manifest = project.joinpath("pyproject.toml").read_bytes()
        identity = f"{project}\n{sys.version}".encode()
        fingerprint = hashlib.sha256(identity + manifest).hexdigest()
        if (
            stamp.is_file()
            and stamp.read_text(encoding="ascii") == fingerprint
            and importlib.util.find_spec("homelimiter") is not None
        ):
            return 0
        print("Installing HomeLimiter dependencies in .venv…", flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "-e", str(project)], check=True)
        stamp.write_text(fingerprint, encoding="ascii")
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError):
        print(
            "HomeLimiter: dependency setup failed. Check pip, internet access and write access to .venv. "
            "If the environment is broken, rename .venv and rerun the launcher.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

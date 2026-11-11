import json
import os
import secrets
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from .models import Model


class Settings(Model):
    adapter: str = "readonly"
    onboarded: bool = False
    inventory_interface: str | None = None
    agent_url: str | None = None
    agent_token_file: str | None = None
    agent_ca_file: str | None = None
    authorized_cidrs: list[str] = Field(default_factory=list)
    protected_addresses: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_settings(self):
        import ipaddress

        if self.adapter not in {"readonly", "mock", "gateway", "bridge"}:
            raise ValueError("Unknown adapter")
        for network in self.authorized_cidrs:
            ipaddress.ip_network(network, strict=True)
        for address in self.protected_addresses:
            ipaddress.ip_address(address)
        if self.adapter == "gateway" and not self.agent_url:
            raise ValueError("An agent URL is required")
        if self.agent_url:
            parts = urlsplit(self.agent_url)
            local = parts.hostname in {"127.0.0.1", "::1"}
            if (
                parts.username
                or parts.password
                or parts.query
                or parts.fragment
                or parts.path not in {"", "/"}
            ):
                raise ValueError("Use a bare agent origin, without credentials or path")
            if not parts.hostname or (parts.scheme != "https" and not (parts.scheme == "http" and local)):
                raise ValueError("Agent requires verified HTTPS or literal loopback SSH tunnel")
            if not self.agent_token_file:
                raise ValueError("A separate agent token file is required")
        return self


def state_dir(demo: bool = False) -> Path:
    default = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "HomeLimiter"
    root = Path(os.environ.get("HOMELIMITER_HOME", default))
    return root / "demo" if demo else root


def private_path(path: Path, directory: bool = False):
    """Restrict credentials/state to the current account. Fail if ACL setup fails."""
    if os.name == "nt":
        import csv

        identity = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=True
        )
        sid = next(csv.reader([identity.stdout.strip()]))[1]
        grant = f"*{sid}:" + ("(OI)(CI)F" if directory else "F")
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", grant], capture_output=True, check=True
        )
    else:
        path.chmod(0o700 if directory else 0o600)


def initialize(root: Path) -> str:
    root.mkdir(parents=True, exist_ok=True)
    private_path(root, directory=True)
    token_path = root / "admin.token"
    try:
        fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(secrets.token_urlsafe(32))
    private_path(token_path)
    config = root / "config.json"
    if not config.exists():
        config.write_text(Settings().model_dump_json(indent=2), encoding="utf-8")
    token = token_path.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise ValueError("Admin credential is too short; restore or regenerate the private token file")
    return token


def load_settings(root: Path, demo=False) -> Settings:
    path = root / "config.json"
    settings = (
        Settings.model_validate(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else Settings()
    )
    if demo:
        return Settings(adapter="mock", onboarded=settings.onboarded)
    if settings.adapter == "mock":
        raise ValueError("Run with --demo to use the isolated simulation profile")
    return settings


def save_settings(root: Path, settings: Settings):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=root, mode="w", encoding="utf-8", delete=False) as file:
            temporary = Path(file.name)
            file.write(settings.model_dump_json(indent=2) + "\n")
        temporary.replace(root / "config.json")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

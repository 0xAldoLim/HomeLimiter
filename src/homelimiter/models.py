from datetime import UTC, datetime, time
from enum import StrEnum
from typing import Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress, field_validator, model_validator


def now() -> datetime:
    return datetime.now(UTC)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Mode(StrEnum):
    FULL = "FULL CONTROL"
    PARTIAL = "PARTIAL CONTROL"
    MONITOR = "MONITOR ONLY"
    DEMO = "DEMO MODE"


class Capabilities(Model):
    adapter: str
    mode: Mode
    discovery: bool = True
    bandwidth: bool = False
    access: bool = False
    ipv6: bool = False
    statistics: bool = False
    simulated: bool = False
    reason: str


class Device(Model):
    id: str
    nickname: str = Field(default="Unknown device", min_length=1, max_length=80)
    addresses: list[IPvAnyAddress] = Field(default_factory=list, max_length=64)
    address_status: dict[str, str] = Field(default_factory=dict, max_length=64)
    mac: str | None = None
    interface: str = ""
    source: str
    status: str = "unknown"
    last_seen: datetime = Field(default_factory=now)
    vendor: str | None = None
    confirmed: bool = False
    protected: bool = False
    simulated: bool = False

    @field_validator("mac")
    @classmethod
    def valid_mac(cls, value):
        if value is None:
            return value
        import re

        value = value.replace("-", ":").lower()
        if not re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", value):
            raise ValueError("Invalid MAC address")
        if int(value[:2], 16) & 1 or value == "00:00:00:00:00:00":
            raise ValueError("A unicast MAC is required")
        return value


class Window(Model):
    timezone: str = "UTC"
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)), min_length=1, max_length=7)
    start: time
    end: time

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown IANA timezone") from exc
        return value

    @field_validator("weekdays")
    @classmethod
    def valid_days(cls, value):
        if any(d < 0 or d > 6 for d in value) or len(set(value)) != len(value):
            raise ValueError("Weekdays must be unique integers 0 (Monday) through 6")
        return value

    @model_validator(mode="after")
    def different_times(self) -> Self:
        if self.start == self.end or self.start.tzinfo or self.end.tzinfo:
            raise ValueError("Use distinct, local start/end times")
        return self


class PolicySpec(Model):
    device_id: str = Field(min_length=1, max_length=100)
    label: str = Field(default="Custom policy", min_length=1, max_length=80)
    download_mbps: float | None = Field(default=None, ge=0.008, le=10000, allow_inf_nan=False)
    upload_mbps: float | None = Field(default=None, ge=0.008, le=10000, allow_inf_nan=False)
    blocked: bool = False
    enabled: bool = True
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    window: Window | None = None

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        if not self.blocked and self.download_mbps is None and self.upload_mbps is None:
            raise ValueError("Choose a bandwidth limit or an internet pause")
        for value in (self.starts_at, self.expires_at):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("Timestamps must include a timezone")
        if self.starts_at and self.expires_at and self.starts_at >= self.expires_at:
            raise ValueError("Expiry must be after start")
        return self


class Policy(PolicySpec):
    id: str
    created_at: datetime = Field(default_factory=now)


class PolicyRequest(PolicySpec):
    confirm_device_id: str | None = None
    dry_run: bool = False


class DeviceUpdate(Model):
    nickname: str | None = Field(default=None, min_length=1, max_length=80)
    confirm_identity: bool = False
    protect: bool = False


class Effective(Model):
    device: Device
    download_mbps: float | None = Field(default=None, ge=0.008, le=10000, allow_inf_nan=False)
    upload_mbps: float | None = Field(default=None, ge=0.008, le=10000, allow_inf_nan=False)
    blocked: bool = False


class Snapshot(Model):
    policies: list[Effective] = Field(default_factory=list, max_length=512)
    lease_seconds: int = Field(default=90, ge=15, le=300)


class Confirmation(Model):
    confirm: bool = False

from datetime import timedelta

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Checkbox, DataTable, Input, Select, Static

from .models import Device, DeviceUpdate, Effective, Policy, PolicyRequest, PolicySpec, Window, now
from .terminal_widgets import Button, Confirm, Dialog, cell, clean, error_message

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
PRESETS = {"Light browsing": ("2", "1"), "Video call": ("5", "2"), "Streaming": ("20", "5")}


def device_state(device: Device) -> str:
    return "Protected" if device.protected else clean(device.status.capitalize())


def target(device: Device):
    return f"{clean(device.nickname)}\nID: {clean(device.id)}  ·  MAC: {clean(device.mac or 'Unavailable')}"


def policy_description(policy: PolicySpec | Effective):
    parts = []
    if policy.blocked:
        parts.append("Pause")
    if policy.download_mbps is not None:
        parts.append(f"↓ {policy.download_mbps:g} Mbps")
    if policy.upload_mbps is not None:
        parts.append(f"↑ {policy.upload_mbps:g} Mbps")
    return " · ".join(parts)


def actionable(device: Device):
    return device.confirmed and not device.protected and device.status == "online"


class DeviceDetail(Dialog):
    def __init__(self, device: Device, view):
        super().__init__()
        self.device = device
        self.view = view
        self.caps = view.status["capabilities"]
        self.policies = [p for p in view.policies if p.device_id == device.id]

    def compose(self) -> ComposeResult:
        device = self.device
        applied = next((entry for entry in self.view.applied if entry.device.id == device.id), None)
        eligible = actionable(device)
        can_limit, can_pause = self.caps["bandwidth"] and eligible, self.caps["access"] and eligible
        with VerticalScroll(classes="dialog"):
            yield Static(target(device), classes="heading", markup=False)
            yield Static(
                "\n".join(
                    [
                        f"Connection: {clean(device.status)}",
                        f"Interface: {clean(device.interface or 'Unavailable')}",
                        f"Last seen: {device.last_seen.astimezone():%Y-%m-%d %H:%M:%S %Z}",
                        f"Identity: {'Confirmed' if device.confirmed else 'Unconfirmed'}",
                        "Protected infrastructure" if device.protected else "Not marked as infrastructure",
                        "Addresses:",
                        *(
                            f"  {clean(address)}  ({clean(device.address_status.get(str(address), 'unverified'))})"
                            for address in device.addresses
                        ),
                    ]
                ),
                markup=False,
            )
            yield Static(
                f"Limits: {'available' if can_limit else 'unavailable'}  ·  "
                f"Pause: {'available' if can_pause else 'unavailable'}\n"
                + (
                    ("Simulated policy: " if self.caps["simulated"] else "Agent acknowledged: ")
                    + policy_description(applied)
                    + "\nCovered bindings: "
                    + ", ".join(map(str, applied.device.addresses))
                    if applied
                    else "No current restriction confirmed for this device."
                ),
                classes="hint",
                markup=False,
            )
            if not eligible:
                yield Static("Restrictions require an online, confirmed, unprotected device.", classes="hint")
            elif not (can_limit or can_pause):
                yield Static(clean(self.caps["reason"]), classes="hint", markup=False)
            with Horizontal(classes="buttons"):
                yield Button("Identity", id="identity", compact=True)
                yield Button("Limit", id="limit", disabled=not can_limit, compact=True)
                yield Button("Pause", id="pause", disabled=not can_pause, compact=True)
                yield Button("Schedule", id="schedule", disabled=not (can_limit or can_pause), compact=True)
            with Horizontal(classes="buttons"):
                yield Button("Saved policies", id="saved", disabled=not self.policies, compact=True)
                yield Button("Restore all", id="restore", disabled=not self.policies, compact=True)
                yield Button("Back", id="cancel", compact=True)
            yield Static("", id="dialog-error", classes="error", markup=False)

    @on(Button.Pressed, "#identity")
    def identity(self):
        self.app.push_screen(IdentityForm(self.device))

    @on(Button.Pressed, "#limit, #pause, #schedule")
    def policy(self, event: Button.Pressed):
        self.app.push_screen(PolicyForm(self.device, event.button.id, self.caps))

    @on(Button.Pressed, "#saved")
    def saved(self):
        self.app.push_screen(PolicyList(self.device, self.policies, self.caps))

    @on(Button.Pressed, "#restore")
    def restore(self):
        self.app.confirm_change(
            "Restore this device?",
            f"{target(self.device)}\n\nRemove {len(self.policies)} saved policies, including future schedules.",
            lambda: self.app.control.resume(self.device.id),
            self,
            "Restore",
        )


class IdentityForm(Dialog):
    def __init__(self, device: Device):
        super().__init__()
        self.device = device

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="dialog"):
            yield Static(target(self.device), classes="heading", markup=False)
            yield Static("Nickname")
            yield Input(clean(self.device.nickname), id="nickname", max_length=80, compact=True)
            yield Checkbox(
                "I verified this MAC and device",
                id="verified",
                disabled=self.device.status != "online" or not self.device.mac,
            )
            yield Checkbox("Protect as infrastructure", id="protect", disabled=self.device.protected)
            yield Static("Protection removes current eligibility for restrictions.", classes="hint")
            yield Static("", id="dialog-error", classes="error", markup=False)
            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="cancel", compact=True)
                yield Button("Save identity", id="save-identity", variant="primary", compact=True)

    @on(Button.Pressed, "#save-identity")
    def save(self):
        try:
            patch = DeviceUpdate(
                nickname=self.query_one("#nickname", Input).value.strip(),
                confirm_identity=self.query_one("#verified", Checkbox).value,
                protect=self.query_one("#protect", Checkbox).value,
            )
        except ValueError as exc:
            self.error(error_message(exc))
            return
        self.app.commit_change(lambda: self.app.control.update_device(self.device.id, patch), self)


class PolicyList(Dialog):
    def __init__(self, device: Device, policies: list[Policy], caps: dict):
        super().__init__()
        self.device, self.policies, self.caps = device, policies, caps

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="dialog"):
            yield Static("Saved policies · " + clean(self.device.nickname), classes="heading", markup=False)
            yield Static("Select a row and press Enter to edit or remove it.", classes="hint")
            yield DataTable(id="device-policies", cursor_type="row", classes="short-table")
            yield Button("Back", id="cancel", compact=True)

    def on_mount(self):
        table = self.query_one(DataTable)
        table.add_columns("Policy", "Restriction", "Timing")
        for policy in self.policies:
            table.add_row(
                cell(policy.label),
                cell(policy_description(policy)),
                cell(
                    "Weekly"
                    if policy.window
                    else "Timed"
                    if policy.expires_at or policy.starts_at
                    else "Always"
                ),
                key=policy.id,
            )
        table.focus()

    @on(DataTable.RowSelected)
    def open_policy(self, event):
        policy = next(p for p in self.policies if p.id == event.row_key.value)
        self.app.push_screen(PolicyOptions(self.device, policy, self.caps))


class PolicyOptions(Dialog):
    def __init__(self, device: Device, policy: Policy, caps: dict):
        super().__init__()
        self.device, self.policy, self.caps = device, policy, caps

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="dialog"):
            yield Static(clean(self.policy.label), classes="heading", markup=False)
            yield Static(f"{target(self.device)}\n{policy_description(self.policy)}", markup=False)
            if self.policy.window:
                window = self.policy.window
                yield Static(
                    f"{', '.join(DAYS[d] for d in window.weekdays)} · "
                    f"{window.start:%H:%M}–{window.end:%H:%M} · {clean(window.timezone)}",
                    markup=False,
                )
            for label, value in (("Starts", self.policy.starts_at), ("Expires", self.policy.expires_at)):
                if value:
                    yield Static(f"{label}: {value.isoformat()}", markup=False)
            with Horizontal(classes="buttons"):
                yield Button("Back", id="cancel", compact=True)
                yield Button(
                    "Edit",
                    id="edit",
                    compact=True,
                    disabled=not actionable(self.device)
                    or not (self.caps["bandwidth"] or self.caps["access"]),
                )
                yield Button("Remove", id="remove", variant="warning", compact=True)
            yield Static("", id="dialog-error", classes="error", markup=False)

    @on(Button.Pressed, "#edit")
    def edit(self):
        self.app.push_screen(PolicyForm(self.device, "edit", self.caps, self.policy))

    @on(Button.Pressed, "#remove")
    def remove_policy(self):
        self.app.confirm_change(
            "Remove this policy?",
            f"{target(self.device)}\n\n{clean(self.policy.label)} · {policy_description(self.policy)}",
            lambda: self.app.control.remove_policy(self.policy.id),
            self,
            "Remove",
        )


class PolicyForm(Dialog):
    def __init__(self, device: Device, kind: str, caps: dict, previous: Policy | None = None):
        super().__init__()
        self.device, self.kind, self.caps, self.previous = device, kind, caps, previous
        self.timed = kind in {"schedule", "edit"}

    def compose(self) -> ComposeResult:
        p = self.previous
        with VerticalScroll(classes="dialog"):
            heading = {
                "limit": "Bandwidth limit",
                "pause": "Pause internet",
                "schedule": "Schedule a restriction",
                "edit": "Edit policy",
            }
            yield Static(heading[self.kind], classes="heading")
            yield Static(target(self.device), markup=False)
            if self.caps["simulated"]:
                yield Static("Demo: changes affect only simulated devices.", classes="hint")
            yield Static("Policy name")
            yield Input(
                clean(p.label)
                if p
                else {"limit": "Bandwidth cap", "pause": "Temporary pause", "schedule": "Bedtime"}[self.kind],
                id="label",
                compact=True,
                max_length=80,
            )
            if self.timed:
                yield Checkbox(
                    "Pause internet access",
                    id="blocked",
                    value=p.blocked if p else bool(self.caps["access"]),
                    disabled=not self.caps["access"],
                )
                yield Checkbox("Policy enabled", value=p.enabled if p else True, id="enabled")
            if self.kind != "pause" and (self.caps["bandwidth"] or p and (p.download_mbps or p.upload_mbps)):
                yield Static("Speed preset (optional)")
                yield Select(
                    [(f"{name}: {down} down / {up} up", name) for name, (down, up) in PRESETS.items()],
                    id="preset",
                    prompt="Custom rates",
                    compact=True,
                    disabled=not self.caps["bandwidth"],
                )
                yield Static("Download Mbps (blank for no cap)")
                yield Input(str(p.download_mbps) if p and p.download_mbps else "", id="down", compact=True)
                yield Static("Upload Mbps (blank for no cap)")
                yield Input(str(p.upload_mbps) if p and p.upload_mbps else "", id="up", compact=True)
            if not self.timed:
                yield Static("Duration in minutes" + ("" if self.kind == "pause" else " (optional)"))
                yield Input("30" if self.kind == "pause" else "", id="minutes", compact=True)
            else:
                window = p.window if p else None
                yield Checkbox("Repeat weekly", value=bool(window) or p is None, id="repeat")
                with Vertical(id="weekly"):
                    yield Static("Start and end (24-hour local time; an earlier end is next day)")
                    with Horizontal(classes="pair"):
                        yield Input(window.start.isoformat() if window else "22:00", id="start", compact=True)
                        yield Input(window.end.isoformat() if window else "07:00", id="end", compact=True)
                    yield Static("Start days (Mon through Sun, separated by commas)")
                    yield Input(
                        ",".join(DAYS[d] for d in window.weekdays) if window else ",".join(DAYS),
                        id="days",
                        compact=True,
                    )
                    yield Static("IANA timezone, e.g. Asia/Kuala_Lumpur or UTC")
                    yield Input(window.timezone if window else "UTC", id="zone", compact=True)
                yield Static("First start (optional ISO date with offset, e.g. 2027-01-02T22:00+08:00)")
                yield Input(
                    p.starts_at.isoformat() if p and p.starts_at else "", id="starts-at", compact=True
                )
                yield Static("Final expiry (optional ISO date with offset)")
                yield Input(
                    p.expires_at.isoformat() if p and p.expires_at else "", id="expires-at", compact=True
                )
            yield Static(
                "Overlapping policies: pause wins, then the lowest cap in each direction.", classes="hint"
            )
            yield Static("", id="dialog-error", classes="error", markup=False)
            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="cancel", compact=True)
                yield Button("Review", id="review", variant="primary", compact=True)

    def on_mount(self):
        if self.timed:
            self.query_one("#weekly").display = self.query_one("#repeat", Checkbox).value

    @on(Checkbox.Changed, "#repeat")
    def repeat_changed(self, event):
        self.query_one("#weekly").display = event.value

    @on(Select.Changed, "#preset")
    def preset(self, event):
        if event.value in PRESETS:
            down, up = PRESETS[event.value]
            self.query_one("#down", Input).value = down
            self.query_one("#up", Input).value = up

    def field(self, identifier):
        return next((item.value.strip() for item in self.query(Input) if item.id == identifier), "")

    def request(self):
        window = None
        expiry = self.field("expires-at") or None
        if not self.timed:
            duration = self.field("minutes")
            if duration or self.kind == "pause":
                try:
                    minutes = int(duration)
                except ValueError as exc:
                    raise ValueError("Enter a whole number of minutes (1–10080).") from exc
                if not 1 <= minutes <= 10080:
                    raise ValueError("Duration must be between 1 and 10080 minutes.")
                expiry = now() + timedelta(minutes=minutes)
        elif self.query_one("#repeat", Checkbox).value:
            days = {day.casefold(): index for index, day in enumerate(DAYS)}
            try:
                selected = [days[day.strip().casefold()] for day in self.field("days").split(",")]
            except KeyError as exc:
                raise ValueError("Enter days as Mon, Tue, Wed, Thu, Fri, Sat, Sun.") from exc
            window = Window(
                start=self.field("start"),
                end=self.field("end"),
                weekdays=selected,
                timezone=self.field("zone"),
            )
        starts = self.field("starts-at") or None
        if self.kind == "schedule" and not (window or starts or expiry):
            raise ValueError("Choose a weekly window or a start/expiry time.")
        return PolicyRequest(
            device_id=self.device.id,
            confirm_device_id=self.device.id,
            label=self.field("label"),
            download_mbps=self.field("down") or None,
            upload_mbps=self.field("up") or None,
            blocked=self.query_one("#blocked", Checkbox).value if self.timed else self.kind == "pause",
            enabled=self.query_one("#enabled", Checkbox).value if self.timed else True,
            starts_at=starts,
            expires_at=expiry,
            window=window,
        )

    @on(Button.Pressed, "#review")
    def review(self):
        try:
            request = self.request()
        except ValueError as exc:
            self.error(error_message(exc))
            return
        timing = (
            f"Weekly: {', '.join(DAYS[d] for d in request.window.weekdays)} "
            f"{request.window.start:%H:%M}–{request.window.end:%H:%M} {clean(request.window.timezone)}"
            if request.window
            else "Applies now"
            if not request.starts_at
            else "Starts at the specified time"
        )
        details = [target(self.device), "", policy_description(request), timing]
        if request.starts_at:
            details.append(f"Starts: {request.starts_at.isoformat()}")
        if request.expires_at:
            details.append(f"Expires: {request.expires_at.isoformat()}")
        if not request.enabled:
            details.append("Saved disabled.")
        if self.caps["simulated"]:
            details.append("Simulated only.")
        identifier = self.previous.id if self.previous else None
        self.app.push_screen(
            Confirm("Save this restriction?", "\n".join(details), "Save"),
            lambda yes: (
                self.app.commit_change(lambda: self.app.control.save_policy(request, identifier), self)
                if yes
                else None
            ),
        )

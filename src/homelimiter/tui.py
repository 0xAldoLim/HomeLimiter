"""Textual presentation for the local or headless controller."""

import asyncio
import json
import sqlite3
import subprocess

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.theme import Theme
from textual.widgets import Button, DataTable, Footer, Input, Select, Static, TabbedContent, TabPane

from .control import LocalControl, RemoteControl, View
from .models import Device
from .onboarding import SetupWizard, diagnostics_text
from .terminal_forms import DeviceDetail, PolicyOptions, device_state, policy_description
from .terminal_widgets import Confirm, cell, clean, error_message

EXPECTED_ERRORS = (ValueError, RuntimeError, OSError, KeyError, sqlite3.Error, subprocess.SubprocessError)

CONSOLE = Theme(
    name="homelimiter",
    primary="#71d7c4",
    accent="#9ce7d8",
    warning="#f5c274",
    error="#ff998e",
    foreground="#e6edf4",
    background="#101921",
    surface="#17232c",
    panel="#233442",
)


class HomeLimiter(App):
    TITLE = "HomeLimiter"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("1", "section('home')", "Home", show=False),
        Binding("2", "section('devices')", "Devices", show=False),
        Binding("3", "section('schedules')", "Schedules", show=False),
        Binding("4", "section('network')", "Network", show=False),
        Binding("5", "section('activity')", "Activity", show=False),
        Binding("r", "refresh", "Refresh"),
        Binding("question_mark", "help", "Help", key_display="?"),
        Binding("q", "quit", "Quit"),
    ]
    CSS = """
    Screen { background: $surface; }
    #banner { background: $primary-background; color: $text; text-style: bold; padding: 0 1; height: 1; }
    #sections { height: 1fr; }
    TabPane { padding: 0 1; }
    .heading { text-style: bold; color: $accent; margin: 1 0; }
    .hint { color: $text-muted; height: auto; }
    .error, #feedback { color: $warning; height: auto; max-height: 3; }
    #feedback { padding: 0 1; }
    #filters { height: 3; }
    #search { width: 1fr; }
    #sort { width: 23; }
    DataTable { height: 1fr; margin-top: 1; }
    ModalScreen { align: center middle; }
    .dialog { width: 74; max-width: 98%; height: auto; max-height: 95%; padding: 0 2 1 2;
              border: solid $accent; background: $surface; }
    .wizard { height: 94%; }
    .wizard-body { height: 1fr; }
    .dialog Vertical, .dialog ContentSwitcher { height: auto; }
    .dialog Input, .dialog Select { margin-bottom: 1; }
    .buttons, .pair { height: auto; margin-top: 1; }
    .buttons Button { min-width: 8; margin-right: 1; }
    .pair Input { width: 1fr; }
    .short-table { height: 8; }
    """

    def __init__(self, control: LocalControl | RemoteControl, *, poll_interval: float = 15):
        super().__init__()
        self.register_theme(CONSOLE)
        self.theme = CONSOLE.name
        self.control = control
        self.poll_interval = poll_interval
        self.busy = False
        self.demo_requested = False
        self.devices: list[Device] = []
        self.snapshot: View | None = None

    def compose(self) -> ComposeResult:
        yield Static("HomeLimiter  /  Loading controller", id="banner", markup=False)
        with TabbedContent(id="sections"):
            with TabPane("1 Home", id="home"):
                with VerticalScroll():
                    yield Static("Network overview", classes="heading")
                    yield Static("Reading inventory and controller status…", id="overview", markup=False)
            with TabPane("2 Devices", id="devices"):
                with Horizontal(id="filters"):
                    yield Input(placeholder="Filter by name, IP, MAC or ID", id="search")
                    yield Select(
                        [("Sort: name", "name"), ("Sort: connection", "state"), ("Sort: last seen", "seen")],
                        value="name",
                        allow_blank=False,
                        id="sort",
                    )
                yield Static("↑/↓ Select   Enter Details   Tab Change focus", classes="hint")
                yield DataTable(id="inventory", cursor_type="row", zebra_stripes=True)
                yield Static("", id="device-count", classes="hint", markup=False)
            with TabPane("3 Schedules", id="schedules"):
                yield Static("Schedule windows and upcoming changes", classes="heading")
                yield Static(
                    "Enter edits or removes a saved rule. To create one, open a device and choose Schedule.",
                    classes="hint",
                )
                yield DataTable(id="schedule-table", cursor_type="row", zebra_stripes=True)
                yield Static("", id="schedule-summary", classes="hint", markup=False)
            with TabPane("4 Network", id="network"):
                with VerticalScroll():
                    yield Static("Network settings", classes="heading")
                    yield Static("", id="network-summary", markup=False)
                    with Horizontal(classes="buttons"):
                        yield Button(
                            "Setup wizard", id="setup", compact=True, disabled=not self.control.can_configure
                        )
                        yield Button("Diagnostics", id="diagnose", compact=True)
                    yield Static("", id="diagnostics", markup=False)
                    yield Button("Emergency restore", id="emergency", variant="warning", compact=True)
            with TabPane("5 Activity", id="activity"):
                with VerticalScroll():
                    yield Static("Recent activity", classes="heading")
                    yield Static("", id="events", markup=False)
        yield Static("", id="feedback", markup=False)
        yield Footer()

    def widget(self, selector, widget_type=None):
        return self.main_screen.query_one(selector, widget_type)

    def on_mount(self):
        self.main_screen = self.screen
        self.widget("#inventory", DataTable).add_columns(
            "Device", "Connection", "First address", "MAC", "Last seen"
        )
        self.widget("#schedule-table", DataTable).add_columns(
            "Policy / device", "Rule", "Window", "Next change"
        )
        self.submit(self.control.view, self.initial_view)
        if self.poll_interval:
            self.set_interval(self.poll_interval, self.poll)

    def initial_view(self, view):
        self.render_view(view)
        if self.control.needs_setup:
            self.push_screen(SetupWizard(self.control))

    def poll(self):
        if len(self.screen_stack) == 1 and not self.busy:
            self.submit(self.control.view, self.render_view)

    def action_section(self, section: str):
        self.widget("#sections", TabbedContent).active = section
        if section == "devices":
            self.widget("#inventory").focus()
        elif section == "schedules":
            self.widget("#schedule-table").focus()

    def action_help(self):
        self.notify(
            "1–5: switch sections. Tab: move through controls. Arrow keys: move through rows. "
            "Enter: open or activate. Escape: close a dialog. R: refresh. Q: quit.",
            title="Keyboard help",
            timeout=12,
        )

    def action_refresh(self):
        if not self.busy:
            self.submit(self.control.refresh, self.render_view)

    def submit(self, operation, done, failed=None):
        if self.busy:
            self.notify("Wait for the current controller operation to finish.", timeout=3)
            return False
        self.busy = True
        self.run_operation(operation, done, failed or self.report_error)
        return True

    @work(exit_on_error=False)
    async def run_operation(self, operation, done, failed):
        try:
            result = await asyncio.to_thread(operation)
        except EXPECTED_ERRORS as exc:
            self.busy = False
            failed(error_message(exc))
        else:
            self.busy = False
            done(result)
        finally:
            self.busy = False

    def report_error(self, message):
        self.widget("#feedback", Static).update(message)
        self.notify(message, severity="error", timeout=7)

    def commit_change(self, operation, dialog=None):
        def execute():
            operation()
            return self.control.view()

        def done(view):
            while len(self.screen_stack) > 1:
                self.pop_screen()
            self.render_view(view)
            self.notify(
                "Saved in demo only." if view.status["capabilities"]["simulated"] else "Controller updated."
            )

        self.submit(execute, done, dialog.error if dialog is not None else self.report_error)

    def confirm_change(self, title, description, operation, dialog=None, verb="Confirm"):
        self.push_screen(
            Confirm(title, description, verb),
            lambda yes: self.commit_change(operation, dialog) if yes else None,
        )

    def setup_complete(self, view):
        self.pop_screen()
        self.render_view(view)
        self.action_section("home")
        self.notify("Setup saved.")

    def open_demo(self):
        self.demo_requested = True
        self.exit()

    def render_view(self, view: View):
        self.snapshot = view
        self.devices = view.devices
        status, caps = view.status, view.status["capabilities"]
        self.widget("#banner", Static).update(f"HomeLimiter  /  {clean(caps['mode'])}")
        count = status["acknowledged_devices"]
        count_label = "unverified" if count is None else str(count)
        lease = status["lease_remaining_seconds"]
        self.widget("#overview", Static).update(
            f"Devices       {sum(d.status == 'online' for d in self.devices)} online / {len(self.devices)} known\n"
            f"Restrictions  {count_label} affected devices / {len(view.policies)} saved policies\n"
            f"Enforcement   {clean(status['enforcement'])}\n"
            f"Scheduler     {clean(view.scheduler)}\n"
            f"Last tick     {clean((status['last_reconciled'] or 'Pending').replace('T', ' '))}\n"
            + (
                f"Lease         ~{lease} seconds remaining after last acknowledgement\n"
                if lease is not None
                else ""
            )
            + f"\n{clean(caps['reason'])}\n\n"
            "2 Devices: inspect and manage   3 Schedules: review timing   4 Network: setup"
        )
        settings = view.settings
        scope = ", ".join(settings.get("authorized_cidrs", [])) or "none configured"
        if caps["adapter"] == "gateway":
            scope = "Defined on the managed agent"
        self.widget("#network-summary", Static).update(
            f"Adapter: {clean(caps['adapter'])} · {clean(caps['mode'])}\n"
            f"Monitor interface: {clean(settings.get('inventory_interface') or 'All scoped interfaces')}\n"
            f"Authorized scope: {clean(scope)}\n"
            f"Bandwidth limits: {'Available' if caps['bandwidth'] else 'Unavailable'}\n"
            f"Internet pause: {'Available' if caps['access'] else 'Unavailable'}\n"
            f"Traffic statistics: {clean(status['statistics'])}\n\n{clean(caps['reason'])}\n"
            + (
                ""
                if self.control.can_configure
                else "Use a local terminal with the service stopped to change settings.\n"
            )
        )
        names = {device.id: device.nickname for device in view.devices}
        self.widget("#events", Static).update(
            "\n\n".join(self.format_event(row, names) for row in view.logs) or "No activity yet."
        )
        self.widget("#feedback", Static).update(clean(status["last_error"] or ""))
        self.update_inventory()
        self.update_schedules()

    @staticmethod
    def format_event(row, names):
        detail = json.loads(row["detail"])
        if isinstance(detail, dict):
            pieces = []
            if identifier := detail.get("device_id"):
                pieces.append(names.get(identifier, identifier))
            if label := detail.get("label"):
                pieces.append(label)
            if reason := detail.get("reason"):
                pieces.append(reason)
            if "devices" in detail:
                pieces.append(
                    f"{detail['devices']} affected devices" + (" (demo)" if detail.get("simulated") else "")
                )
            if not pieces:
                pieces.append(", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in detail.items()))
            detail = " · ".join(pieces)
        return (
            f"{clean(row['time'][:19]).replace('T', ' ')}Z  {clean(row['outcome'])}  "
            f"{clean(row['action'].replace('.', ' '))}\n  {clean(detail)}"
        )

    @on(Input.Changed, "#search")
    @on(Select.Changed, "#sort")
    def filter_changed(self):
        if hasattr(self, "main_screen"):
            self.update_inventory()

    def update_inventory(self):
        search = self.widget("#search", Input).value.strip().casefold()
        sort = self.widget("#sort", Select).value
        table = self.widget("#inventory", DataTable)
        if not table.columns:
            return
        previous = table.coordinate_to_cell_key(table.cursor_coordinate).row_key if table.row_count else None
        table.clear()
        rows = [
            d
            for d in self.devices
            if search in " ".join([d.nickname, d.id, d.mac or "", *map(str, d.addresses)]).casefold()
        ]
        if sort == "seen":
            rows.sort(key=lambda d: d.last_seen, reverse=True)
        elif sort == "state":
            rows.sort(key=lambda d: (d.status != "online", d.nickname.casefold()))
        else:
            rows.sort(key=lambda d: d.nickname.casefold())
        for device in rows:
            table.add_row(
                cell(device.nickname),
                cell(device_state(device)),
                cell(device.addresses[0] if device.addresses else "—"),
                cell(device.mac or "—"),
                cell(device.last_seen.astimezone().strftime("%d %b %H:%M")),
                key=device.id,
            )
        if previous is not None and any(d.id == previous.value for d in rows):
            table.move_cursor(row=table.get_row_index(previous))
        note = " · Check Network setup or refresh the passive cache" if not self.devices else ""
        self.widget("#device-count", Static).update(f"{len(rows)} of {len(self.devices)} devices{note}")

    def update_schedules(self):
        table = self.widget("#schedule-table", DataTable)
        previous = table.coordinate_to_cell_key(table.cursor_coordinate).row_key if table.row_count else None
        table.clear()
        policies = {p.id: p for p in self.snapshot.policies}
        names = {d.id: d.nickname for d in self.devices}
        for schedule in self.snapshot.schedules:
            policy = policies[schedule.policy_id]
            table.add_row(
                cell(f"{policy.label} / {names.get(policy.device_id, policy.device_id)}"),
                cell(policy_description(policy)),
                cell("Disabled" if not policy.enabled else "Open" if schedule.active else "Closed"),
                cell(schedule.next_action or "—"),
                key=policy.id,
            )
        if previous is not None and any(s.policy_id == previous.value for s in self.snapshot.schedules):
            table.move_cursor(row=table.get_row_index(previous))
        self.widget("#schedule-summary", Static).update(
            f"{table.row_count} scheduled policies · Window state does not verify traffic enforcement."
            if table.row_count
            else "No scheduled policies."
        )

    @on(DataTable.RowSelected, "#inventory")
    def open_device(self, event: DataTable.RowSelected):
        device = next((d for d in self.devices if d.id == event.row_key.value), None)
        if device:
            self.push_screen(DeviceDetail(device, self.snapshot))

    @on(DataTable.RowSelected, "#schedule-table")
    def open_schedule(self, event: DataTable.RowSelected):
        policy = next((p for p in self.snapshot.policies if p.id == event.row_key.value), None)
        if policy:
            device = next((d for d in self.devices if d.id == policy.device_id), None)
            if device is None:
                device = Device(id=policy.device_id, source="saved policy", status="offline")
            self.push_screen(PolicyOptions(device, policy, self.snapshot.status["capabilities"]))

    @on(Button.Pressed, "#setup")
    def setup(self):
        if not self.busy:
            self.push_screen(SetupWizard(self.control))

    @on(Button.Pressed, "#diagnose")
    def diagnose(self):
        self.submit(
            self.control.diagnostics,
            lambda data: self.widget("#diagnostics", Static).update(diagnostics_text(data)),
        )

    @on(Button.Pressed, "#emergency")
    def emergency(self):
        self.confirm_change(
            "Restore all HomeLimiter restrictions?",
            "Remove every saved policy in this profile, including future schedules, and request agent recovery.",
            self.control.emergency,
            verb="Restore all",
        )

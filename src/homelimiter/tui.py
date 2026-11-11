"""Terminal presentation. Inventory and policy decisions belong to the controller."""

import asyncio
import unicodedata

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Input, Select, Static, TabbedContent, TabPane

from .models import Device
from .service import Service


def clean(value) -> str:
    """Display external text literally, without terminal controls or bidi overrides."""
    return "".join(c for c in str(value) if unicodedata.category(c) not in {"Cc", "Cf", "Cs"})


def device_state(device: Device) -> str:
    return "Protected" if device.protected else clean(device.status.capitalize())


def cell(value) -> Text:
    return Text(clean(value))


class DeviceDetail(ModalScreen):
    BINDINGS = [("escape", "dismiss", "Back")]

    def __init__(self, device: Device):
        super().__init__()
        self.device = device

    def compose(self) -> ComposeResult:
        device = self.device
        with VerticalScroll(classes="dialog"):
            yield Static(clean(device.nickname), classes="heading", markup=False)
            yield Static(
                "\n".join(
                    [
                        f"Device ID: {clean(device.id)}",
                        f"Connection: {device_state(device)}",
                        f"MAC: {clean(device.mac or 'Unavailable')}",
                        f"Interface: {clean(device.interface or 'Unavailable')}",
                        f"Last seen: {device.last_seen.astimezone():%Y-%m-%d %H:%M:%S %Z}",
                        f"Identity: {'Confirmed' if device.confirmed else 'Unconfirmed'}",
                        "Addresses:",
                        *(f"  {clean(address)}" for address in device.addresses),
                    ]
                ),
                markup=False,
            )
            yield Button("Back", id="close-detail")

    @on(Button.Pressed, "#close-detail")
    def close_detail(self):
        self.dismiss()


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
    #feedback { color: $warning; height: auto; max-height: 3; padding: 0 1; }
    #filters { height: 3; }
    #search { width: 1fr; }
    #sort { width: 24; }
    DataTable { height: 1fr; margin-top: 1; }
    ModalScreen { align: center middle; }
    .dialog { width: 74; max-width: 98%; height: auto; max-height: 95%; padding: 0 2 1 2;
              border: solid $accent; background: $surface; }
    .dialog Button { margin-top: 1; }
    """

    def __init__(self, service: Service, *, poll_interval: float = 15):
        super().__init__()
        self.service = service
        self.poll_interval = poll_interval
        self.busy = False
        self.devices: list[Device] = []

    def compose(self) -> ComposeResult:
        yield Static(" HomeLimiter   /   Loading controller", id="banner", markup=False)
        with TabbedContent(id="sections"):
            with TabPane("1 Home", id="home"):
                with VerticalScroll():
                    yield Static("Network overview", classes="heading")
                    yield Static("Reading inventory and controller status…", id="overview", markup=False)
            with TabPane("2 Devices", id="devices"):
                with Horizontal(id="filters"):
                    yield Input(placeholder="Filter by name, IP, MAC or ID", id="search")
                    yield Select(
                        [("Name", "name"), ("Connection", "state"), ("Last seen", "seen")],
                        value="name",
                        allow_blank=False,
                        id="sort",
                    )
                yield Static("↓/↑  Select     Enter  Details     Tab  Change focus", classes="hint")
                yield DataTable(id="inventory", cursor_type="row", zebra_stripes=True)
                yield Static("", id="device-count", classes="hint")
            with TabPane("3 Schedules", id="schedules"):
                with VerticalScroll():
                    yield Static("Scheduled restrictions", classes="heading")
                    yield Static("", id="schedule-summary", markup=False)
            with TabPane("4 Network", id="network"):
                with VerticalScroll():
                    yield Static("Network capabilities", classes="heading")
                    yield Static("", id="network-summary", markup=False)
            with TabPane("5 Activity", id="activity"):
                with VerticalScroll():
                    yield Static("Recent activity", classes="heading")
                    yield Static("", id="events", markup=False)
        yield Static("", id="feedback", markup=False)
        yield Footer()

    def on_mount(self):
        self.query_one("#inventory", DataTable).add_columns(
            "Device", "Connection", "First address", "MAC", "Last seen"
        )
        self.action_refresh()
        if self.poll_interval:
            self.set_interval(self.poll_interval, self.action_refresh)

    def action_section(self, section: str):
        self.query_one("#sections", TabbedContent).active = section
        if section == "devices":
            self.query_one("#inventory").focus()

    def action_help(self):
        self.notify(
            "1–5: switch screens. Tab: move between controls. Arrow keys: move through rows. "
            "Enter: open or activate. Escape: close a dialog. R: refresh. Q: quit.",
            title="Keyboard help",
            timeout=12,
        )

    def action_refresh(self):
        if not self.busy:
            self.busy = True
            self.refresh_view()

    def read_view(self):
        self.service.tick()
        return (
            self.service.status(),
            self.service.devices(),
            self.service.store.policies(),
            self.service.store.logs(limit=60),
        )

    @work(exit_on_error=False)
    async def refresh_view(self):
        try:
            status, self.devices, policies, logs = await asyncio.to_thread(self.read_view)
            caps = status["capabilities"]
            self.query_one("#banner", Static).update(f" HomeLimiter   /   {clean(caps['mode'])}")
            self.query_one("#overview", Static).update(
                f"{sum(d.status == 'online' for d in self.devices)} observed online · "
                f"{len(self.devices)} known devices\n"
                f"{len(policies)} saved policies\n"
                f"Last reconciliation: {clean(status['last_reconciled'] or 'Pending')}\n\n"
                f"{clean(caps['reason'])}\n\n"
                "Press 2 to inspect the device inventory."
            )
            self.query_one("#network-summary", Static).update(
                f"Adapter: {clean(caps['adapter'])}\n"
                f"Bandwidth limits: {'Available' if caps['bandwidth'] else 'Unavailable'}\n"
                f"Internet pause: {'Available' if caps['access'] else 'Unavailable'}\n"
                f"Traffic statistics: {clean(status['statistics'])}\n\n{clean(caps['reason'])}"
            )
            self.query_one("#schedule-summary", Static).update(
                "\n".join(
                    f"{clean(p.label)} · {clean(p.device_id)}"
                    for p in policies
                    if p.window or p.starts_at or p.expires_at
                )
                or "No scheduled policies."
            )
            self.query_one("#events", Static).update(
                "\n".join(
                    f"{clean(row['time'][:19])}Z  {clean(row['outcome'])}  {clean(row['action'])}\n"
                    f"    {clean(row['detail'])}"
                    for row in logs
                )
                or "No activity yet."
            )
            self.query_one("#feedback", Static).update(clean(status["last_error"] or ""))
            self.update_inventory()
        except (ValueError, RuntimeError, OSError) as exc:
            self.query_one("#feedback", Static).update(clean(exc))
        finally:
            self.busy = False

    @on(Input.Changed, "#search")
    @on(Select.Changed, "#sort")
    def filter_changed(self):
        self.update_inventory()

    def update_inventory(self):
        search = self.query_one("#search", Input).value.strip().casefold()
        sort = self.query_one("#sort", Select).value
        table = self.query_one("#inventory", DataTable)
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
        self.query_one("#device-count", Static).update(f"{len(rows)} of {len(self.devices)} devices")

    @on(DataTable.RowSelected, "#inventory")
    def open_device(self, event: DataTable.RowSelected):
        device = next((d for d in self.devices if d.id == event.row_key.value), None)
        if device:
            self.push_screen(DeviceDetail(device))

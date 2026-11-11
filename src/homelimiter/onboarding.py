"""First-run setup; discovers passively and never provisions network paths."""

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Checkbox, ContentSwitcher, DataTable, Input, Select, Static

from .config import Settings
from .models import Device, DeviceUpdate
from .terminal_forms import device_state, target
from .terminal_widgets import Button, Dialog, cell, clean, error_message

MODES = [
    ("Monitor only — passive local inventory", "readonly"),
    ("Demo — isolated simulated devices", "mock"),
    ("Existing authorized gateway agent", "agent"),
    ("Managed Linux gateway — connect a provisioned agent", "gateway"),
    ("Linux bridge — monitor only", "bridge"),
]


def diagnostics_text(data: dict):
    lines = [
        f"{clean(data['os'])} {clean(data['release'])} · Python {clean(data['python'])}",
        f"Administrator: {'yes' if data['administrator'] else 'no'}",
        f"System or virtualization hint: {clean(data['virtualization'])}",
        "",
        "Default routes:",
    ]
    for family in ("ipv4", "ipv6"):
        routes = data[f"default_routes_{family}"]
        for route in routes[:8]:
            lines.append(
                f"  {family.upper()} {clean(route.get('dev', '?'))} via {clean(route.get('gateway', 'on link'))}"
            )
        if not routes:
            lines.append(f"  {family.upper()}: unavailable")
    lines.append("\nInterfaces:")
    for entry in data["interface_choices"]:
        networks = ", ".join(entry["networks"]) or "no suggested networks"
        lines.append(f"  {clean(entry['name'])} ({'up' if entry['up'] else 'down'}): {clean(networks)}")
    if data["os"] == "Linux":
        lines.append("\nLinux tools: " + ", ".join(tool for tool, found in data["tools"].items() if found))
    lines.append("\n" + clean(data["note"]))
    return "\n".join(lines)


class SetupIdentity(Dialog):
    def __init__(self, device, existing=None):
        super().__init__()
        self.device, self.existing = device, existing

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="dialog"):
            yield Static(target(self.device), classes="heading", markup=False)
            yield Static("Addresses: " + ", ".join(map(str, self.device.addresses)), markup=False)
            yield Static("Nickname")
            yield Input(
                clean(self.existing.nickname if self.existing else self.device.nickname),
                id="setup-nickname",
                max_length=80,
                compact=True,
            )
            yield Checkbox(
                "I verified this MAC and device",
                id="setup-verified",
                value=bool(self.existing and self.existing.confirm_identity),
                disabled=self.device.status != "online" or not self.device.mac,
            )
            yield Checkbox(
                "Protect as infrastructure",
                id="setup-protect",
                value=bool(self.existing and self.existing.protect),
                disabled=self.device.protected,
            )
            yield Static("", id="dialog-error", classes="error", markup=False)
            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="cancel", compact=True)
                yield Button("Keep for setup", id="keep-identity", compact=True, variant="primary")

    @on(Button.Pressed, "#keep-identity")
    def keep_identity(self):
        try:
            patch = DeviceUpdate(
                nickname=self.query_one("#setup-nickname", Input).value.strip(),
                confirm_identity=self.query_one("#setup-verified", Checkbox).value,
                protect=self.query_one("#setup-protect", Checkbox).value,
            )
        except ValueError as exc:
            self.error(error_message(exc))
            return
        self.dismiss(patch)


class SetupWizard(Dialog):
    steps = ("Environment", "Operating mode", "Network scope", "Initial inventory", "Finish")

    def __init__(self, control):
        super().__init__()
        self.control = control
        self.initial = control.settings
        self.mode = "agent" if self.initial.adapter == "gateway" else self.initial.adapter
        self.step = 0
        self.diagnostics = {}
        self.inventory: list[Device] = []
        self.identities: dict[str, DeviceUpdate] = {}
        self.draft = None
        self.caps = None

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wizard"):
            yield Static("", id="setup-title", classes="heading", markup=False)
            with VerticalScroll(classes="wizard-body"):
                with ContentSwitcher(initial="environment", id="setup-pages"):
                    with Vertical(id="environment"):
                        yield Static("Checking this computer…", id="environment-result", markup=False)
                    with Vertical(id="mode"):
                        yield Static("Select a mode. No option changes routes or enables forwarding.")
                        modes = [entry for entry in MODES if not self.control.demo or entry[1] == "mock"]
                        yield Select(modes, id="setup-mode", value=self.mode, allow_blank=False, compact=True)
                        yield Static("", id="mode-help", classes="hint", markup=False)
                    with Vertical(id="scope"):
                        with Vertical(id="monitor-fields"):
                            yield Static("Interface (choose a name or keep all selected networks)")
                            yield Select(
                                [("All interfaces in authorized CIDRs", "")],
                                value="",
                                id="setup-interface",
                                allow_blank=False,
                                compact=True,
                            )
                            yield Button("Use selected interface subnets", id="suggest", compact=True)
                            yield Static(
                                "Authorized IPv4/IPv6 CIDRs (comma separated; blank disables discovery)"
                            )
                            yield Input(
                                ", ".join(self.initial.authorized_cidrs), id="setup-cidrs", compact=True
                            )
                            yield Static("Protected addresses (optional, comma separated)")
                            yield Input(
                                ", ".join(self.initial.protected_addresses),
                                id="setup-protected",
                                compact=True,
                            )
                        with Vertical(id="agent-fields"):
                            yield Static(
                                "Use an already provisioned Linux agent. See docs/LINUX_SETUP.md. "
                                "This wizard checks connectivity only; it never provisions the gateway.",
                                classes="hint",
                            )
                            yield Static("Agent origin (HTTPS or a literal loopback SSH tunnel)")
                            yield Input(self.initial.agent_url or "", id="setup-url", compact=True)
                            yield Static("Path to the private agent token file")
                            yield Input(
                                self.initial.agent_token_file or "", id="setup-token-file", compact=True
                            )
                            yield Static("Trusted CA certificate path (blank uses system trust)")
                            yield Input(self.initial.agent_ca_file or "", id="setup-ca", compact=True)
                        yield Static("", id="scope-note", classes="hint", markup=False)
                        yield Checkbox("I am authorized to manage this scope", id="setup-authorized")
                    with Vertical(id="initial-devices"):
                        yield Static("", id="preview-note", markup=False)
                        yield DataTable(id="setup-inventory", cursor_type="row", classes="short-table")
                    with Vertical(id="finish"):
                        yield Static("", id="setup-summary", markup=False)
            yield Static("", id="dialog-error", classes="error", markup=False)
            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="cancel", compact=True)
                yield Button("Back", id="setup-back", compact=True)
                yield Button("Continue", id="setup-next", variant="primary", compact=True, disabled=True)

    def on_mount(self):
        self.query_one("#setup-inventory", DataTable).add_columns("Device", "Connection", "MAC")
        self.show_step(0)
        self.call_after_refresh(self.load_environment)

    def load_environment(self):
        def loaded(data):
            self.diagnostics = data
            select = self.query_one("#setup-mode", Select)
            if not self.control.demo and data["os"] != "Linux" and self.mode != "bridge":
                select.set_options([item for item in MODES if item[1] != "bridge"])
                select.value = self.mode
            status = self.app.snapshot.status["capabilities"]
            self.query_one("#environment-result", Static).update(
                f"Current mode: {clean(status['mode'])}\n\n" + diagnostics_text(data)
            )
            self.show_step(0)
            self.query_one("#setup-next").focus()

        def failed(message):
            self.query_one("#environment-result", Static).update(
                "Environment checks were unavailable. You can still try Demo or supply an explicit scope."
            )
            self.diagnostics = {"interface_choices": []}
            self.show_step(0)
            self.error(message)

        self.app.submit(self.control.diagnostics, loaded, failed)

    def show_step(self, step):
        self.step = step
        self.query_one("#setup-pages", ContentSwitcher).current = (
            "environment",
            "mode",
            "scope",
            "initial-devices",
            "finish",
        )[step]
        self.query_one("#setup-title", Static).update(f"Setup {step + 1}/5 · {self.steps[step]}")
        self.query_one("#dialog-error", Static).update("")
        self.query_one("#setup-back", Button).disabled = step == 0
        next_button = self.query_one("#setup-next", Button)
        next_button.disabled = not self.diagnostics
        next_button.label = ("Continue", "Continue", "Preview inventory", "Continue", "Save setup")[step]
        if step == 1:
            self.mode_help()
        if step == 2:
            self.prepare_scope()
        if step == 3:
            self.update_preview()
        if step == 4:
            self.query_one("#setup-summary", Static).update(
                f"Mode: {clean(self.caps.mode)}\n"
                f"{clean(self.caps.reason)}\n\n"
                f"{len(self.inventory)} observed devices; {len(self.identities)} identity changes to save.\n"
                "No traffic rules are created by setup. Restrictions require a separate confirmed policy."
            )
        self.query_one(".wizard-body", VerticalScroll).scroll_home(animate=False)

    @on(Select.Changed, "#setup-mode")
    def mode_changed(self, event):
        if isinstance(event.value, str):
            self.mode = event.value
            self.mode_help()

    def mode_help(self):
        self.query_one("#mode-help", Static).update(
            {
                "readonly": "Works without administrator privileges. Reads only cached neighbors within explicitly authorized networks.",
                "mock": "A separate profile with simulated devices and policies. Use --demo to reopen it.",
                "agent": "Requires a reachable authorized routed Linux agent and its separate credential.",
                "gateway": "Requires two routed interfaces and an independently provisioned Linux agent. "
                "A Windows laptop or a bridged VM is not a gateway for unrelated devices.",
                "bridge": "Bridge traffic enforcement is unavailable. This option monitors a selected local interface only.",
            }[self.mode]
        )

    def prepare_scope(self):
        agent = self.mode in {"gateway", "agent"}
        self.query_one("#agent-fields").display = agent
        self.query_one("#monitor-fields").display = not agent and self.mode != "mock"
        self.query_one("#setup-authorized").display = self.mode != "mock"
        self.query_one("#scope-note", Static).update(
            "The agent defines its authorized LAN and protected addresses."
            if agent
            else "Demo has no network interface or CIDR requirements."
            if self.mode == "mock"
            else "Only the system's neighbor cache is read. A passive list may be empty or incomplete."
        )
        select = self.query_one("#setup-interface", Select)
        selected = select.value or self.initial.inventory_interface or ""
        choices = [("All interfaces in authorized CIDRs", "")]
        choices.extend(
            (f"{clean(item['name'])} ({'up' if item['up'] else 'down'})", item["id"])
            for item in self.diagnostics["interface_choices"]
        )
        select.set_options(choices)
        select.value = selected if selected in {value for _, value in choices} else ""

    @on(Button.Pressed, "#suggest")
    def suggest(self):
        chosen = self.query_one("#setup-interface", Select).value
        item = next((item for item in self.diagnostics["interface_choices"] if item["id"] == chosen), None)
        if not item or not item["networks"]:
            self.error("Select an interface with a suggested subnet, or enter an authorized CIDR yourself.")
            return
        self.query_one("#setup-cidrs", Input).value = ", ".join(item["networks"])

    def make_settings(self):
        def field(identifier):
            return self.query_one(f"#setup-{identifier}", Input).value.strip()

        def values(identifier):
            return [part.strip() for part in field(identifier).split(",") if part.strip()]

        def path(identifier):
            return str(Path(field(identifier)).expanduser().resolve()) if field(identifier) else None

        authorized = self.query_one("#setup-authorized", Checkbox).value
        if self.mode in {"agent", "gateway"}:
            if not authorized:
                raise ValueError("Confirm you are authorized to use this agent.")
            return Settings(
                adapter="gateway",
                onboarded=True,
                agent_url=field("url") or None,
                agent_token_file=path("token-file"),
                agent_ca_file=path("ca"),
            )
        if self.mode == "mock":
            return Settings(adapter="mock", onboarded=True)
        cidrs = values("cidrs")
        if cidrs and not authorized:
            raise ValueError("Confirm you are authorized to observe these CIDRs.")
        return Settings(
            adapter=self.mode,
            onboarded=True,
            inventory_interface=self.query_one("#setup-interface", Select).value or None,
            authorized_cidrs=cidrs,
            protected_addresses=values("protected"),
        )

    def preview(self):
        try:
            settings = self.make_settings()
        except (ValueError, OSError) as exc:
            self.error(error_message(exc))
            return

        def loaded(result):
            if settings != self.draft:
                self.identities.clear()
            self.draft = settings
            self.inventory, self.caps = result
            self.show_step(3)
            if self.inventory:
                self.query_one("#setup-inventory").focus()
            else:
                self.query_one("#setup-next").focus()

        self.run_setup_job(lambda: self.control.preview(settings), loaded)

    def run_setup_job(self, operation, done):
        button = self.query_one("#setup-next", Button)
        button.disabled = True

        def succeeded(value):
            if self.is_mounted:
                button.disabled = False
                done(value)

        def failed(message):
            if self.is_mounted:
                button.disabled = False
                self.error(message)

        if not self.app.submit(operation, succeeded, failed):
            button.disabled = False

    def update_preview(self):
        self.query_one("#preview-note", Static).update(
            f"{clean(self.caps.mode)} · {len(self.inventory)} devices\n"
            + (
                "Press Enter on a row to confirm identity or add a nickname."
                if self.inventory
                else "The cache has no matching devices yet. You can finish and refresh later."
            )
        )
        table = self.query_one("#setup-inventory", DataTable)
        table.clear()
        for device in self.inventory:
            patch = self.identities.get(device.id)
            table.add_row(
                cell(patch.nickname if patch else device.nickname),
                cell(device_state(device)),
                cell(device.mac or "Unavailable"),
                key=device.id,
            )

    @on(DataTable.RowSelected, "#setup-inventory")
    def identify(self, event):
        device = next(item for item in self.inventory if item.id == event.row_key.value)

        def keep(patch):
            if patch is not None:
                self.identities[device.id] = patch
                self.update_preview()

        self.app.push_screen(SetupIdentity(device, self.identities.get(device.id)), keep)

    @on(Button.Pressed, "#setup-back")
    def back(self):
        if not self.app.busy:
            self.show_step(self.step - 1)

    @on(Button.Pressed, "#setup-next")
    def next(self):
        if self.app.busy:
            return
        if self.step == 1 and self.mode == "mock" and not self.control.demo:
            self.app.open_demo()
        elif self.step == 2:
            self.preview()
        elif self.step == 4:
            self.run_setup_job(
                lambda: self.control.configure(self.draft, self.identities),
                self.app.setup_complete,
            )
        else:
            self.show_step(self.step + 1)

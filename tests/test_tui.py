import asyncio

from textual.widgets import Button, Checkbox, DataTable, Input, Select, Static, TabbedContent

from homelimiter.adapters import MockAdapter, ReadOnlyAdapter
from homelimiter.config import Settings, initialize, load_settings
from homelimiter.control import LocalControl
from homelimiter.onboarding import SetupWizard
from homelimiter.service import Service
from homelimiter.store import Store
from homelimiter.terminal_forms import DeviceDetail, PolicyForm, PolicyOptions
from homelimiter.terminal_widgets import Confirm
from homelimiter.tui import HomeLimiter


async def press_button(pilot, identifier):
    pilot.app.screen.query_one(identifier, Button).focus()
    await pilot.press("enter")


async def ready(pilot):
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


def test_keyboard_inventory(service):
    async def scenario():
        app = HomeLimiter(LocalControl(service), poll_interval=0)
        async with app.run_test(size=(80, 24)) as pilot:
            await ready(pilot)
            assert "DEMO MODE" in str(app.query_one("#banner", Static).content)
            await pilot.press("2")
            assert app.query_one(TabbedContent).active == "devices"
            table = app.query_one("#inventory", DataTable)
            assert app.focused is table and table.row_count == 4
            await pilot.press("down", "enter")
            assert isinstance(app.screen, DeviceDetail)
            assert app.screen.device.id == "demo-2"
            await pilot.press("escape")
            app.query_one("#search", Input).focus()
            await pilot.press("g", "a", "m")
            assert table.row_count == 1
            app.query_one("#search", Input).value = "Management"
            table.focus()
            await pilot.press("enter")
            assert app.screen.query_one("#pause", Button).disabled
            assert app.screen.query_one("#limit", Button).disabled

    asyncio.run(scenario())


def test_keyboard_limit_validation_confirmation_and_removal(service):
    async def scenario():
        app = HomeLimiter(LocalControl(service), poll_interval=0)
        async with app.run_test(size=(80, 24)) as pilot:
            await ready(pilot)
            await pilot.press("2", "down", "enter")
            await press_button(pilot, "#limit")
            assert isinstance(app.screen, PolicyForm)
            app.screen.query_one("#down", Input).value = "0"
            await press_button(pilot, "#review")
            assert "0.008" in str(app.screen.query_one("#dialog-error", Static).content)
            app.screen.query_one("#preset", Select).value = "Video call"
            await pilot.pause()
            await press_button(pilot, "#review")
            assert isinstance(app.screen, Confirm)
            await pilot.press("enter")  # Cancellation is focused by default.
            assert not service.store.policies()
            await press_button(pilot, "#review")
            await press_button(pilot, "#confirm")
            await ready(pilot)
            policy = service.store.policies()[0]
            assert (policy.device_id, policy.download_mbps, policy.upload_mbps) == ("demo-2", 5, 2)
            assert app.snapshot.status["acknowledged_devices"] == 1

            await pilot.press("2", "enter")
            await press_button(pilot, "#saved")
            await pilot.press("enter")
            assert isinstance(app.screen, PolicyOptions)
            await press_button(pilot, "#remove")
            await press_button(pilot, "#confirm")
            await ready(pilot)
            assert not service.store.policies()
            assert not service.adapter.get_active_policies()

    asyncio.run(scenario())


def test_schedule_creation_and_edit(service):
    async def scenario():
        app = HomeLimiter(LocalControl(service), poll_interval=0)
        async with app.run_test(size=(68, 20)) as pilot:
            await ready(pilot)
            await pilot.press("2", "enter")
            await press_button(pilot, "#schedule")
            app.screen.query_one("#zone", Input).value = "Asia/Kuala_Lumpur"
            await press_button(pilot, "#review")
            await press_button(pilot, "#confirm")
            await ready(pilot)
            policy = service.store.policies()[0]
            assert policy.blocked and policy.window.timezone == "Asia/Kuala_Lumpur"
            assert app.snapshot.schedules[0].next_action
            await pilot.press("3", "enter")
            await press_button(pilot, "#edit")
            app.screen.query_one("#end", Input).value = "06:30"
            await press_button(pilot, "#review")
            await press_button(pilot, "#confirm")
            await ready(pilot)
            edited = service.store.policies()[0]
            assert edited.id == policy.id and edited.window.end.isoformat() == "06:30:00"

    asyncio.run(scenario())


def test_first_run_demo_setup_and_rerun(tmp_path, monkeypatch):
    root = tmp_path / "demo"
    initialize(root)
    control = LocalControl(
        Service(Store(root / "controller.db"), MockAdapter()), load_settings(root, True), root
    )
    monkeypatch.setattr(
        control,
        "diagnostics",
        lambda: {
            "os": "Windows",
            "release": "test",
            "python": "3.12",
            "administrator": False,
            "virtualization": "VMware",
            "default_routes_ipv4": [],
            "default_routes_ipv6": [],
            "interface_choices": [],
            "note": "Passive diagnostics only.",
        },
    )

    async def scenario():
        app = HomeLimiter(control, poll_interval=0)
        async with app.run_test(size=(80, 24)) as pilot:
            await ready(pilot)
            await ready(pilot)
            assert isinstance(app.screen, SetupWizard)
            assert app.screen.step == 0
            await press_button(pilot, "#setup-next")
            await press_button(pilot, "#setup-next")
            await press_button(pilot, "#setup-next")
            await ready(pilot)
            assert app.screen.step == 3
            await pilot.press("down", "enter")
            app.screen.query_one("#setup-nickname", Input).value = "Test television"
            await press_button(pilot, "#keep-identity")
            await press_button(pilot, "#setup-next")
            await press_button(pilot, "#setup-next")
            await ready(pilot)
            assert app.screen is app.main_screen
            assert load_settings(root, True).onboarded
            assert control.service.device("demo-2").nickname == "Test television"
            assert not (tmp_path / "controller.db").exists()
            await pilot.press("4")
            await press_button(pilot, "#setup")
            await ready(pilot)
            assert isinstance(app.screen, SetupWizard)

    asyncio.run(scenario())


def test_monitor_setup_requires_scope_authorization(tmp_path, monkeypatch):
    initialize(tmp_path)
    control = LocalControl(
        Service(Store(tmp_path / "controller.db"), ReadOnlyAdapter(Settings())), Settings(), tmp_path
    )
    monkeypatch.setattr(
        control,
        "diagnostics",
        lambda: {
            "os": "Linux",
            "release": "test",
            "python": "3.12",
            "administrator": False,
            "virtualization": "none",
            "default_routes_ipv4": [{"dev": "lan0", "gateway": "192.0.2.1"}],
            "default_routes_ipv6": [],
            "interface_choices": [{"id": "lan0", "name": "lan0", "up": True, "networks": ["192.0.2.0/24"]}],
            "tools": {},
            "note": "Passive diagnostics only.",
        },
    )
    monkeypatch.setattr("homelimiter.adapters.neighbors", lambda interface: [])

    async def scenario():
        app = HomeLimiter(control, poll_interval=0)
        async with app.run_test(size=(80, 24)) as pilot:
            await ready(pilot)
            await ready(pilot)
            await press_button(pilot, "#setup-next")
            await press_button(pilot, "#setup-next")
            app.screen.query_one("#setup-interface", Select).value = "lan0"
            await press_button(pilot, "#suggest")
            await press_button(pilot, "#setup-next")
            assert "authorized" in str(app.screen.query_one("#dialog-error", Static).content)
            assert not load_settings(tmp_path).authorized_cidrs
            app.screen.query_one("#setup-authorized", Checkbox).value = True
            await press_button(pilot, "#setup-next")
            await ready(pilot)
            await press_button(pilot, "#setup-next")
            await press_button(pilot, "#setup-next")
            await ready(pilot)
            assert load_settings(tmp_path).authorized_cidrs == ["192.0.2.0/24"]
            assert load_settings(tmp_path).inventory_interface == "lan0"
            assert "MONITOR ONLY" in str(app.widget("#banner", Static).content)

    asyncio.run(scenario())

import asyncio

from textual.widgets import DataTable, Input, Static, TabbedContent

from homelimiter.tui import DeviceDetail, HomeLimiter


def test_keyboard_inventory(service):
    async def scenario():
        app = HomeLimiter(service, poll_interval=0)
        async with app.run_test(size=(80, 24)) as pilot:
            await app.workers.wait_for_complete()
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

    asyncio.run(scenario())

"""Real browser smoke test against a disposable demo server; no live network changes."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from homelimiter.config import initialize

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        os.environ.get("HOMELIMITER_BROWSER_TESTS") != "1", reason="Opt in with HOMELIMITER_BROWSER_TESTS=1"
    ),
]


def test_dashboard_end_to_end(tmp_path):
    from playwright.sync_api import sync_playwright

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    token = initialize(tmp_path / "demo")
    command = [
        sys.executable,
        "-m",
        "homelimiter.cli",
        "--home",
        str(tmp_path),
        "--demo",
        "dashboard",
        "--port",
        str(port),
    ]
    server = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    origin = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(origin, timeout=1, trust_env=False).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            pytest.fail("Demo server did not start")
        with sync_playwright() as pw:
            executable = os.environ.get("HOMELIMITER_BROWSER_EXE")
            browser = pw.chromium.launch(headless=True, executable_path=executable)
            page = browser.new_page(viewport={"width": 1440, "height": 1050})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(origin)
            page.get_by_label("Admin token", exact=True).fill(token)
            page.get_by_role("button", name="Open your dashboard").click()
            page.get_by_role("heading", name="A clearer view of your network.").wait_for()
            page.locator("#mode").get_by_text("DEMO MODE", exact=True).wait_for()
            assert page.locator("#token").input_value() == ""
            screenshot = os.environ.get("HOMELIMITER_SCREENSHOT")
            if screenshot:
                page.screenshot(path=screenshot, full_page=True)
            for target in (
                "devices",
                "bandwidth",
                "access",
                "scheduling",
                "agents",
                "diagnostics",
                "logs",
                "settings",
            ):
                page.locator(f'.nav-link[href="#{target}"]').click()
                page.locator("#breadcrumb").filter(
                    has_text={
                        "devices": "Connected devices",
                        "bandwidth": "Bandwidth",
                        "access": "Internet access",
                        "scheduling": "Scheduling",
                        "agents": "Enforcement agents",
                        "diagnostics": "Network diagnostics",
                        "logs": "Audit logs",
                        "settings": "Settings",
                    }[target]
                ).wait_for()
                assert page.locator("#main").inner_text()
            page.locator('.nav-link[href="#devices"]').click()
            page.get_by_label("Search devices").fill("Gaming")
            assert page.locator(".device-card").count() == 1
            page.get_by_role("link", name="View device").click()
            page.get_by_role("heading", name="Gaming console").wait_for()
            page.get_by_role("button", name="Set a limit", exact=True).click()
            page.get_by_label("Download cap / Mbps").fill("2")
            page.get_by_label("Upload cap / Mbps").fill("1")
            page.get_by_label("I confirm this target is authorized for this restriction.").check()
            page.get_by_role("button", name="Confirm & apply").click()
            page.locator("#modal").wait_for(state="hidden")
            page.get_by_text("Custom limit", exact=False).first.wait_for()
            page.get_by_role("button", name="Edit device", exact=True).click()
            page.get_by_label("Nickname", exact=True).fill("<img src=x onerror=alert(1)>")
            page.get_by_role("button", name="Save device", exact=True).click()
            page.get_by_role("heading", name="<img src=x onerror=alert(1)>", exact=True).wait_for()
            assert page.locator("#main img").count() == 0
            page.locator('.nav-link[href="#scheduling"]').click()
            page.get_by_role("button", name="New schedule").click()
            page.get_by_label("I confirm this target is authorized for this restriction.").check()
            page.get_by_role("button", name="Confirm & apply").click()
            page.locator("#modal").wait_for(state="hidden")
            page.get_by_text("Evening routine", exact=False).first.wait_for()
            page.get_by_label("Toggle color theme").click()
            assert "dark" in page.locator("body").get_attribute("class")
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator('.nav-link[href="#devices"]').click()
            page.get_by_role("heading", name="Your connected devices.").wait_for()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            if screenshot:
                page.screenshot(path=str(Path(screenshot).with_name("dashboard-mobile.png")), full_page=True)
            assert not errors, errors
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=15)

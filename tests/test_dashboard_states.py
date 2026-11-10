"""Browser regressions for responsive navigation and data-state presentation."""

import os
import socket
import subprocess
import sys
import time

import httpx
import pytest

from homelimiter.config import initialize

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        os.environ.get("HOMELIMITER_BROWSER_TESTS") != "1",
        reason="Opt in with HOMELIMITER_BROWSER_TESTS=1",
    ),
]


def test_responsive_navigation_filters_and_connection_states(tmp_path):
    from playwright.sync_api import expect, sync_playwright

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    token = initialize(tmp_path / "demo")
    origin = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "homelimiter.cli",
            "--home",
            str(tmp_path),
            "--demo",
            "dashboard",
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        for _ in range(100):
            try:
                if httpx.get(origin, trust_env=False, timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            pytest.fail("Disposable demo server did not start")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True, executable_path=os.environ.get("HOMELIMITER_BROWSER_EXE")
            )
            page = browser.new_page(viewport={"width": 390, "height": 844})

            def observed_states(route):
                response = route.fetch()
                devices = response.json()
                devices[1]["status"] = "offline"
                devices[2]["status"] = "unknown"
                route.fulfill(response=response, json=devices)

            page.route("**/api/devices", observed_states)

            def login():
                page.get_by_label("Admin token", exact=True).fill(token)
                page.get_by_role("button", name="Open your dashboard").click()
                page.locator('#main[aria-busy="false"] h1').wait_for()

            page.goto(origin)
            login()
            disclosure = page.locator(".navigation-disclosure")
            expect(disclosure).not_to_have_attribute("open", "")
            page.get_by_text("Navigation", exact=True).click()
            page.locator('.nav-link[href="#devices"]').click()
            expect(page.get_by_label("Search devices")).to_be_visible()
            expect(disclosure).not_to_have_attribute("open", "")
            page.get_by_label("Search devices").fill("Gaming")
            expect(page).to_have_url(origin + "/#devices?search=Gaming")
            expect(page.locator(".device-card")).to_have_count(1)
            page.reload()
            login()
            expect(page.get_by_label("Search devices")).to_have_value("Gaming")
            expect(page.locator(".device-card")).to_have_count(1)
            page.set_viewport_size({"width": 1440, "height": 1000})
            expect(page.locator('.nav-link[href="#overview"]')).to_be_visible()
            page.locator('.nav-link[href="#overview"]').click()
            page.get_by_role("heading", name="A clearer view of your network.").wait_for()
            online = page.locator('.connection-status[data-state="online"]').first
            offline = page.locator('.connection-status[data-state="offline"]')
            unknown = page.locator('.connection-status[data-state="unknown"]')
            read_color = "element => getComputedStyle(element).color"
            assert online.evaluate(read_color) != offline.evaluate(read_color)
            assert online.evaluate(read_color) != unknown.evaluate(read_color)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=15)

"""Single owner for controller state and policy reconciliation."""

import logging
import sqlite3
import threading
from pathlib import Path

from .adapters import make_adapter
from .config import Settings, initialize, load_settings
from .control import LocalControl
from .locking import StateLock
from .service import Service
from .store import Store

log = logging.getLogger(__name__)


class Runtime:
    def __init__(
        self,
        root: Path,
        demo=False,
        *,
        service: Service | None = None,
        token: str | None = None,
        interval=15.0,
    ):
        self.root, self.demo = root, demo
        self.service, self.token = service, token
        self.interval = interval
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()

    def __enter__(self):
        if self.token is None:
            self.token = initialize(self.root)
        self.lock = StateLock(self.root)
        try:
            settings = load_settings(self.root, self.demo) if self.service is None else Settings()
            if self.service is None:
                store = Store(self.root / "controller.db")
                self.service = Service(store, make_adapter(settings))
            self.control = LocalControl(self.service, settings, self.root)
            self.control.scheduler = "Stopped (one-shot command)"
        except BaseException:
            self.lock.close()
            raise
        return self

    def start(self, *, headless=False):
        if self.thread is not None:
            raise RuntimeError("Controller scheduler is already running")
        self.control.scheduler = (
            "Running in headless service" if headless else "Running while this terminal stays open"
        )
        self.thread = threading.Thread(target=self.run, name="homelimiter-scheduler")
        self.thread.start()

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.service.tick()
            except (OSError, sqlite3.Error) as exc:
                # A state write or audit failure must not terminate the retry loop.
                with self.service.lock:
                    self.service.last_error = f"Could not write controller state: {exc}"
            self.stop_event.wait(self.interval)

    def __exit__(self, exc_type, exc, traceback):
        try:
            if self.thread is not None:
                self.stop_event.set()
                self.thread.join()
                self.control.scheduler = "Stopped"
                try:
                    self.service.suspend()
                except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
                    log.warning("Controller stopped without verified agent restoration: %s", error)
        finally:
            try:
                self.service.adapter.close()
            finally:
                self.lock.close()

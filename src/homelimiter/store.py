import json
import sqlite3
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path

from .models import Device, Policy, now


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS policies(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit(
                    id INTEGER PRIMARY KEY, time TEXT NOT NULL,
                    action TEXT NOT NULL, outcome TEXT NOT NULL, detail TEXT NOT NULL
                );
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def devices(self) -> list[Device]:
        with self.connection() as db:
            return [
                Device.model_validate_json(r[0]) for r in db.execute("SELECT data FROM devices ORDER BY id")
            ]

    def save_device(self, device: Device):
        self.save_devices([device])

    def save_devices(self, devices: list[Device]):
        with self.connection() as db:
            db.executemany(
                "INSERT INTO devices VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                [(device.id, device.model_dump_json()) for device in devices],
            )

    def policies(self) -> list[Policy]:
        with self.connection() as db:
            return [
                Policy.model_validate_json(r[0]) for r in db.execute("SELECT data FROM policies ORDER BY id")
            ]

    def save_policy(self, policy: Policy):
        self.change_policies(save=[policy])

    def change_policies(self, *, save: Sequence[Policy] = (), delete: Sequence[str] = ()):
        with self.connection() as db:
            db.executemany("DELETE FROM policies WHERE id=?", [(identifier,) for identifier in delete])
            db.executemany(
                "INSERT INTO policies VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                [(policy.id, policy.model_dump_json()) for policy in save],
            )

    def delete_policy(self, policy_id: str):
        self.change_policies(delete=[policy_id])

    def audit(self, action: str, outcome: str, detail: dict | str):
        with self.connection() as db:
            db.execute(
                "INSERT INTO audit(time,action,outcome,detail) VALUES(?,?,?,?)",
                (now().isoformat(), action, outcome, json.dumps(detail, default=str)),
            )

    def logs(self, limit=200):
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (min(limit, 1000),))
            ]

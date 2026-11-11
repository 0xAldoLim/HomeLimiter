import os
from pathlib import Path


class StateLock:
    """An OS lock released on process death; shared by controller entry points."""

    def __init__(self, root: Path):
        self.file = (root / "process.lock").open("a+b")
        self.file.seek(0, os.SEEK_END)
        if self.file.tell() == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise RuntimeError(
                "State is in use. Connect to the headless controller with --connect PORT, or stop the other session."
            ) from exc

    def close(self):
        self.file.close()

"""Protocol seams over the per-service log files and over the clock a follow loop waits on."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ILogSource(Protocol):
    def services(self, log_dir: Path) -> list[str]:
        """Names of the services that have a log file in *log_dir*, sorted."""
        ...

    def poll(self, path: Path, offset: int) -> tuple[list[str], int]:
        """Complete lines written to *path* since *offset*, and the offset to resume from.

        A file shorter than *offset* was truncated; reading restarts from the beginning. A missing file yields no
        lines and offset ``0``. A trailing partial line stays unread until its newline arrives.
        """
        ...


class IFollowClock(Protocol):
    def sleep(self, seconds: float) -> None: ...

    def keep_following(self) -> bool:
        """``False`` ends a follow loop; production never ends it, tests bound it."""
        ...

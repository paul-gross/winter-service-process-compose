"""Protocol seam over finding and killing a dead daemon's orphaned process session."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ISessionReaper(Protocol):
    def find_daemon_sid(self, socket: Path) -> int | None:
        """The session id (== pid) of the daemon whose argv carries *socket*, or ``None``."""
        ...

    def pid_alive(self, pid: int) -> bool: ...

    def reap(self, sid: int) -> int:
        """Terminate every process in session *sid*, escalating to SIGKILL; returns how many were signalled."""
        ...

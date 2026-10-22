"""Protocol seam over the ``process-compose`` binary, plus the process facts it reports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ProcessInfo:
    """One process as reported by ``process list -o json``.

    ``is_ready`` is the raw process-compose value (``Ready``, ``Not Ready``, ``-``); ``start_time`` is the raw
    RFC3339 ``process_start_time`` or ``None`` when the process never started.
    """

    name: str
    status: str
    is_ready: str
    has_ready_probe: bool
    pid: int
    restarts: int
    start_time: str | None


class IProcessComposeClient(Protocol):
    """Every interaction with the binary, addressed at one instance by its socket path."""

    def is_available(self) -> bool:
        """True when the ``process-compose`` binary is on ``PATH``."""
        ...

    def launch(self, socket: Path, config: Path, daemon_log: Path) -> None:
        """Start a detached daemon and wait until it answers on *socket*; raises ``ProcessComposeError``."""
        ...

    def update(self, socket: Path, config: Path) -> None:
        """Apply *config* to the live instance; unchanged processes keep their pid."""
        ...

    def down(self, socket: Path) -> None:
        """Stop every process and the daemon."""
        ...

    def list_processes(self, socket: Path) -> list[ProcessInfo] | None:
        """The instance's processes, or ``None`` when nothing answers on *socket*."""
        ...

    def start_process(self, socket: Path, name: str) -> None: ...

    def stop_process(self, socket: Path, name: str) -> None: ...

    def restart_process(self, socket: Path, name: str) -> None: ...

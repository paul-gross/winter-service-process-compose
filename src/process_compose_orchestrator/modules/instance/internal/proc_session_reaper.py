"""``ISessionReaper`` over ``/proc``: finds a daemon by its socket argv and signals a session's members."""

from __future__ import annotations

import contextlib
import os
import signal
from pathlib import Path

from process_compose_orchestrator.modules.instance.clock import IClock
from process_compose_orchestrator.modules.instance.session_reaper import ISessionReaper

_TERM_GRACE_SECONDS = 3.0
_POLL_SECONDS = 0.1


class ProcSessionReaper:
    def __init__(self, clock: IClock, proc_root: Path = Path("/proc")) -> None:
        self._clock = clock
        self._proc = proc_root

    def find_daemon_sid(self, socket: Path) -> int | None:
        needle = str(socket)
        for pid in self._pids():
            try:
                argv = (self._proc / str(pid) / "cmdline").read_bytes().split(b"\0")
            except OSError:
                continue
            args = [a.decode(errors="replace") for a in argv]
            if needle in args and args and Path(args[0]).name == "process-compose":
                sid = self._sid(pid)
                return sid if sid == pid else None
        return None

    def pid_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        stat = self._stat_fields(pid)
        return stat is None or stat[0] != "Z"

    def reap(self, sid: int) -> int:
        members = self._members(sid)
        for pid in members:
            self._signal(pid, signal.SIGTERM)
        deadline = self._clock.monotonic() + _TERM_GRACE_SECONDS
        while self._members(sid) and self._clock.monotonic() < deadline:
            self._clock.sleep(_POLL_SECONDS)
        for pid in self._members(sid):
            self._signal(pid, signal.SIGKILL)
        return len(members)

    def _members(self, sid: int) -> list[int]:
        return [pid for pid in self._pids() if self._sid(pid) == sid and self.pid_alive(pid)]

    def _pids(self) -> list[int]:
        try:
            return [int(p.name) for p in self._proc.iterdir() if p.name.isdigit()]
        except OSError:
            return []

    def _stat_fields(self, pid: int) -> list[str] | None:
        """Fields after the ``comm`` entry of ``/proc/<pid>/stat``: state, ppid, pgrp, session, ..."""
        try:
            text = (self._proc / str(pid) / "stat").read_text()
        except OSError:
            return None
        return text.rsplit(")", 1)[1].split()

    def _sid(self, pid: int) -> int | None:
        fields = self._stat_fields(pid)
        return int(fields[3]) if fields else None

    @staticmethod
    def _signal(pid: int, sig: signal.Signals) -> None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(pid, sig)


def _conforms_proc_session_reaper(x: ProcSessionReaper) -> ISessionReaper:
    return x

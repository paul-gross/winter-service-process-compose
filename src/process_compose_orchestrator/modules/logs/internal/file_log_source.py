"""Filesystem ``ILogSource`` and wall-clock ``IFollowClock``."""

from __future__ import annotations

import time
from pathlib import Path

from process_compose_orchestrator.modules.logs.log_source import IFollowClock, ILogSource


class FileLogSource:
    def services(self, log_dir: Path) -> list[str]:
        if not log_dir.is_dir():
            return []
        return sorted(p.stem for p in log_dir.glob("*.log") if p.is_file())

    def poll(self, path: Path, offset: int) -> tuple[list[str], int]:
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return [], 0
        start = 0 if size < offset else offset
        if size == start:
            return [], start
        with path.open("rb") as handle:
            handle.seek(start)
            data = handle.read(size - start)
        end = data.rfind(b"\n")
        if end < 0:
            return [], start
        complete = data[: end + 1]
        return complete.decode("utf-8", errors="replace").splitlines(), start + len(complete)


class WallFollowClock:
    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def keep_following(self) -> bool:
        return True


def _conforms_log_source(adapter: FileLogSource) -> ILogSource:
    return adapter


def _conforms_follow_clock(adapter: WallFollowClock) -> IFollowClock:
    return adapter

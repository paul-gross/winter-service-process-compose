"""In-memory fakes for every Protocol seam."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from process_compose_orchestrator.modules.manifest.errors import ManifestError
from process_compose_orchestrator.modules.manifest.model import ExtServices, ServiceManifest


class FakeManifestReader:
    """Returns a canned manifest, or raises when constructed with an error."""

    def __init__(self, manifest: ServiceManifest | None = None, error: ManifestError | None = None) -> None:
        self._manifest = manifest or ServiceManifest()
        self._error = error
        self.read_dirs: list[Path] = []

    def read(self, config_dir: Path) -> ServiceManifest:
        self.read_dirs.append(config_dir)
        if self._error is not None:
            raise self._error
        return self._manifest


class FakeExtManifestReader:
    """Returns canned extension services."""

    def __init__(self, ext: ExtServices | None = None) -> None:
        self._ext = ext or ExtServices()
        self.read_paths: list[Path] = []

    def read(self, path: Path) -> ExtServices:
        self.read_paths.append(path)
        return self._ext


# --- instance module fakes -------------------------------------------------------------------------------------


from contextlib import contextmanager  # noqa: E402

from process_compose_orchestrator.core.scope import Scope  # noqa: E402
from process_compose_orchestrator.modules.instance.instance_state import InstanceState  # noqa: E402
from process_compose_orchestrator.modules.instance.process_compose_client import ProcessInfo  # noqa: E402


def proc(
    name: str,
    status: str = "Running",
    ready: str = "-",
    probe: bool = False,
    pid: int = 100,
    start: str | None = "2026-10-22T06:55:11.130612088-05:00",
) -> ProcessInfo:
    return ProcessInfo(name, status, ready, probe, pid, 0, start)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeNotifier:
    def __init__(self) -> None:
        self.notes: list[str] = []

    def note(self, message: str) -> None:
        self.notes.append(message)


class FakeClient:
    """Models one daemon per socket path; ``alive`` holds the sockets that answer."""

    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.alive: dict[Path, list[ProcessInfo]] = {}
        self.calls: list[tuple[str, ...]] = []
        self.launched_configs: list[dict] = []
        self.updated_configs: list[dict] = []
        self.after_update: list[ProcessInfo] | None = None
        self.on_poll: list[list[ProcessInfo]] = []

    def is_available(self) -> bool:
        return self.available

    def launch(self, socket: Path, config: Path, daemon_log: Path) -> None:
        import json

        self.calls.append(("launch", str(socket)))
        cfg = json.loads(config.read_text())
        self.launched_configs.append(cfg)
        self.alive[socket] = [proc(n, "Disabled") for n in cfg["processes"]]
        socket.parent.mkdir(parents=True, exist_ok=True)
        socket.touch()

    def update(self, socket: Path, config: Path) -> None:
        import json

        self.calls.append(("update", str(socket)))
        cfg = json.loads(config.read_text())
        self.updated_configs.append(cfg)
        current = {p.name: p for p in self.alive[socket]}
        self.alive[socket] = [
            current.get(n, proc(n, "Disabled"))
            if cfg["processes"][n].get("disabled")
            else proc(n, "Running", ready="Ready", probe="readiness_probe" in cfg["processes"][n])
            for n in cfg["processes"]
        ]
        if self.after_update is not None:
            self.alive[socket] = self.after_update

    def down(self, socket: Path) -> None:
        self.calls.append(("down", str(socket)))
        self.alive.pop(socket, None)
        socket.unlink(missing_ok=True)

    def list_processes(self, socket: Path) -> list[ProcessInfo] | None:
        if self.on_poll and socket in self.alive:
            self.alive[socket] = self.on_poll.pop(0)
        return self.alive.get(socket)

    def start_process(self, socket: Path, name: str) -> None:
        self.calls.append(("start", name))
        self.alive[socket] = [
            proc(n, "Running", ready="Ready", probe=True) if n == name else p
            for p in self.alive[socket]
            for n in [p.name]
        ]

    def stop_process(self, socket: Path, name: str) -> None:
        self.calls.append(("stop", name))

    def restart_process(self, socket: Path, name: str) -> None:
        self.calls.append(("restart", name))


class FakeReaper:
    def __init__(self, sid: int | None = 4242, alive_pids: set[int] | None = None) -> None:
        self.sid = sid
        self.alive_pids = alive_pids or set()
        self.reaped: list[int] = []

    def find_daemon_sid(self, socket: Path) -> int | None:
        return self.sid

    def pid_alive(self, pid: int) -> bool:
        return pid in self.alive_pids

    def reap(self, sid: int) -> int:
        self.reaped.append(sid)
        return 3


class FakeStateStore:
    def __init__(self) -> None:
        self.states: dict[str, InstanceState] = {}

    def read(self, scope: Scope) -> InstanceState | None:
        return self.states.get(scope.name)

    def write(self, scope: Scope, state: InstanceState) -> None:
        self.states[scope.name] = state

    def clear(self, scope: Scope) -> None:
        self.states.pop(scope.name, None)

    @contextmanager
    def _held(self) -> Iterator[None]:
        yield

    def lock(self, scope: Scope):
        return self._held()

    def remove_socket(self, socket: Path) -> None:
        socket.unlink(missing_ok=True)

    def socket_exists(self, socket: Path) -> bool:
        return socket.exists()


# --- logs module fakes -----------------------------------------------------------------------------------------


class FakeLogSource:
    """Holds each file's text; ``poll`` mirrors the real adapter's offset and truncation semantics."""

    def __init__(self, files: dict[Path, str] | None = None) -> None:
        self.files: dict[Path, str] = dict(files or {})

    def services(self, log_dir: Path) -> list[str]:
        return sorted(p.stem for p in self.files if p.parent == log_dir)

    def poll(self, path: Path, offset: int) -> tuple[list[str], int]:
        text = self.files.get(path)
        if text is None:
            return [], 0
        start = 0 if len(text) < offset else offset
        end = text.rfind("\n")
        if end < start:
            return [], start
        return text[start : end + 1].splitlines(), end + 1


class FakeFollowClock:
    """Runs ``on_sleep`` each time the loop idles and stops after ``max_sleeps`` idles."""

    def __init__(self, max_sleeps: int = 3, on_sleep=None) -> None:
        self.max_sleeps = max_sleeps
        self.sleeps = 0
        self.on_sleep = on_sleep

    def sleep(self, seconds: float) -> None:
        self.sleeps += 1
        if self.on_sleep is not None:
            self.on_sleep(self.sleeps)

    def keep_following(self) -> bool:
        return self.sleeps <= self.max_sleeps

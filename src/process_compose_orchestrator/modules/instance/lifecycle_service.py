"""Instance lifecycle: up, down, restart, and stale-instance recovery for one scope."""

from __future__ import annotations

import fnmatch
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from process_compose_orchestrator.core.errors import ProcessComposeError
from process_compose_orchestrator.core.patterns import ScopePattern
from process_compose_orchestrator.core.scope import Scope
from process_compose_orchestrator.modules.instance.clock import IClock
from process_compose_orchestrator.modules.instance.config_renderer import ConfigRenderer
from process_compose_orchestrator.modules.instance.instance_state import IInstanceStateStore, InstanceState
from process_compose_orchestrator.modules.instance.notifier import INotifier
from process_compose_orchestrator.modules.instance.process_compose_client import IProcessComposeClient, ProcessInfo
from process_compose_orchestrator.modules.instance.session_reaper import ISessionReaper
from process_compose_orchestrator.modules.instance.socket_layout import SocketLayout
from process_compose_orchestrator.modules.manifest.model import Service

INSTALL_HINT = "install it from https://f1bonacc1.github.io/process-compose/installation/ (requires >= 1.122.0)"
TERMINAL_STATUSES = frozenset({"Completed", "Error", "Skipped", "Disabled"})
_FAILED_STATUSES = frozenset({"Completed", "Error", "Skipped"})
_DEFAULT_TIMEOUT_SECONDS = 120.0
_POLL_SECONDS = 0.5


class InstanceKind(StrEnum):
    ABSENT = "absent"
    LIVE = "live"
    STALE = "stale"


@dataclass(frozen=True)
class InstanceView:
    """What is found for a scope: nothing, a live daemon with its processes, or a stale socket."""

    kind: InstanceKind
    socket: Path
    processes: tuple[ProcessInfo, ...] = ()


class InstanceLifecycleService:
    """Drives one scope's daemon through the seams; every mutation holds the scope's advisory lock."""

    def __init__(
        self,
        client: IProcessComposeClient,
        reaper: ISessionReaper,
        store: IInstanceStateStore,
        layout: SocketLayout,
        renderer: ConfigRenderer,
        clock: IClock,
        notifier: INotifier,
    ) -> None:
        self._client = client
        self._reaper = reaper
        self._store = store
        self._layout = layout
        self._renderer = renderer
        self._clock = clock
        self._notifier = notifier

    def require_binary(self) -> None:
        if not self._client.is_available():
            raise ProcessComposeError(f"the process-compose binary is not on PATH; {INSTALL_HINT}")

    def inspect(self, scope: Scope) -> InstanceView:
        """Classify the scope's instance without changing anything."""
        socket = self._layout.socket_path(scope)
        if not self._store.socket_exists(socket):
            return InstanceView(InstanceKind.ABSENT, socket)
        processes = self._client.list_processes(socket)
        if processes is None:
            return InstanceView(InstanceKind.STALE, socket)
        return InstanceView(InstanceKind.LIVE, socket, tuple(processes))

    def up(
        self,
        scope: Scope,
        services: tuple[Service, ...],
        pattern: ScopePattern,
        environ: Mapping[str, str],
        timeout: float | None = None,
    ) -> None:
        """Start the matched services (all of them for a whole-scope pattern), then wait on declared health."""
        if not services:
            self._notifier.note(f"scope '{scope.name}' declares no services; nothing to start")
            return
        self.require_binary()
        selected = self._select(services, pattern)
        if not selected:
            raise ProcessComposeError(f"no service in scope '{scope.name}' matches '{pattern.service}'")
        deadline_seconds = _DEFAULT_TIMEOUT_SECONDS if timeout is None else timeout
        with self._store.lock(scope):
            view = self.inspect(scope)
            if view.kind is InstanceKind.STALE:
                self._recover(scope, view.socket)
                view = InstanceView(InstanceKind.ABSENT, view.socket)
            scope.log_dir.mkdir(parents=True, exist_ok=True)
            if view.kind is InstanceKind.ABSENT:
                self._fresh_start(scope, services, selected, environ, view.socket)
            else:
                self._update_live(scope, services, selected, environ, view)
            self._await_ready(scope, view.socket, services, selected, deadline_seconds)

    def down(self, scope: Scope, pattern: ScopePattern) -> None:
        """Stop the whole scope, or only the matched processes, leaving the daemon up for a partial pattern."""
        socket = self._layout.socket_path(scope)
        with self._store.lock(scope):
            state = self._store.read(scope)
            if not self._store.socket_exists(socket) and state is None:
                self._notifier.note(f"scope '{scope.name}' has no running instance")
                return
            view = self.inspect(scope)
            if view.kind is InstanceKind.ABSENT or view.kind is InstanceKind.STALE:
                self._recover(scope, socket)
                return
            self.require_binary()
            if pattern.covers_whole_scope:
                self._client.down(socket)
                if state is not None and not self._reaper.pid_alive(state.sid):
                    self._reaper.reap(state.sid)
                self._store.remove_socket(socket)
                self._store.clear(scope)
                return
            names = [p.name for p in view.processes if fnmatch.fnmatchcase(p.name, pattern.service)]
            if not names:
                raise ProcessComposeError(f"no running service in scope '{scope.name}' matches '{pattern.service}'")
            for name in names:
                self._client.stop_process(socket, name)

    def restart(self, scope: Scope, service_globs: list[str]) -> None:
        """Restart the live processes matching *service_globs*; a scope with no live daemon is an error."""
        self.require_binary()
        with self._store.lock(scope):
            view = self.inspect(scope)
            if view.kind is not InstanceKind.LIVE:
                raise ProcessComposeError(
                    f"scope '{scope.name}' has no running instance to restart; run `winter service up {scope.name}`"
                )
            names = [p.name for p in view.processes if any(fnmatch.fnmatchcase(p.name, g) for g in service_globs)]
            if not names:
                raise ProcessComposeError(f"no service in scope '{scope.name}' matches {', '.join(service_globs)}")
            for name in names:
                self._client.restart_process(view.socket, name)

    def _fresh_start(
        self,
        scope: Scope,
        services: tuple[Service, ...],
        selected: set[str],
        environ: Mapping[str, str],
        socket: Path,
    ) -> None:
        # The first `project update` after a launch restarts every process whatever its definition, while later
        # updates only touch real changes. Launching everything disabled and enabling through an update makes that
        # one-time restart a first start, so an unchanged `up` afterwards keeps every pid.
        self._write_config(scope, services, set(), environ)
        self._client.launch(socket, scope.config_path, scope.daemon_log_path)
        sid = self._reaper.find_daemon_sid(socket)
        if sid is None:
            self._notifier.note(f"could not record the daemon session for scope '{scope.name}'; crash recovery limited")
        else:
            self._store.write(scope, InstanceState(sid=sid, socket=str(socket)))
        self._write_config(scope, services, selected, environ)
        self._client.update(socket, scope.config_path)

    def _update_live(
        self,
        scope: Scope,
        services: tuple[Service, ...],
        selected: set[str],
        environ: Mapping[str, str],
        view: InstanceView,
    ) -> None:
        running = {p.name for p in view.processes if p.status not in TERMINAL_STATUSES}
        self._write_config(scope, services, selected | running, environ)
        self._client.update(view.socket, scope.config_path)
        refreshed = self._client.list_processes(view.socket) or []
        for proc in refreshed:
            if proc.name in selected and proc.status in TERMINAL_STATUSES:
                self._client.start_process(view.socket, proc.name)

    def _write_config(
        self, scope: Scope, services: tuple[Service, ...], enabled: set[str], environ: Mapping[str, str]
    ) -> None:
        config = self._renderer.render(scope, services, enabled, environ)
        scope.state_dir.mkdir(parents=True, exist_ok=True)
        tmp = scope.config_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(config, indent=2))
        os.replace(tmp, scope.config_path)

    def _await_ready(
        self, scope: Scope, socket: Path, services: tuple[Service, ...], selected: set[str], timeout: float
    ) -> None:
        awaited = {svc.name for svc in services if svc.name in selected and svc.health is not None}
        if not awaited:
            return
        deadline = self._clock.monotonic() + timeout
        while True:
            by_name = {p.name: p for p in self._client.list_processes(socket) or []}
            failed = sorted(n for n in awaited if n in by_name and by_name[n].status in _FAILED_STATUSES)
            if failed:
                raise ProcessComposeError(f"scope '{scope.name}': service(s) failed before becoming ready: {failed}")
            waiting = sorted(n for n in awaited if n not in by_name or by_name[n].is_ready != "Ready")
            if not waiting:
                return
            if self._clock.monotonic() >= deadline:
                raise ProcessComposeError(
                    f"scope '{scope.name}': not ready after {timeout:g}s: {', '.join(waiting)}; "
                    f"see {scope.log_dir} and {scope.daemon_log_path}"
                )
            self._clock.sleep(_POLL_SECONDS)

    def _recover(self, scope: Scope, socket: Path) -> None:
        """Clear a dead instance: reap its orphaned session (only when the daemon pid is gone), then forget it."""
        state = self._store.read(scope)
        if state is not None:
            if self._reaper.pid_alive(state.sid):
                raise ProcessComposeError(
                    f"scope '{scope.name}': daemon pid {state.sid} is alive but not answering on {socket}"
                )
            reaped = self._reaper.reap(state.sid)
            if reaped:
                self._notifier.note(f"scope '{scope.name}': reaped {reaped} orphaned process(es) of a dead instance")
        self._store.remove_socket(socket)
        self._store.clear(scope)

    @staticmethod
    def _select(services: tuple[Service, ...], pattern: ScopePattern) -> set[str]:
        """Matched service names plus their transitive same-scope dependencies."""
        by_name = {svc.name: svc for svc in services}
        pending = [svc.name for svc in services if fnmatch.fnmatchcase(svc.name, pattern.service)]
        selected: set[str] = set()
        while pending:
            name = pending.pop()
            if name in selected:
                continue
            selected.add(name)
            pending.extend(by_name[name].depends_on)
        return selected

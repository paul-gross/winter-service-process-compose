"""Builds the env-keyed status document for one scope."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from process_compose_orchestrator.core.patterns import ScopePattern, matches
from process_compose_orchestrator.core.scope import Scope
from process_compose_orchestrator.modules.instance.lifecycle_service import InstanceKind, InstanceLifecycleService
from process_compose_orchestrator.modules.instance.notifier import INotifier
from process_compose_orchestrator.modules.manifest.model import Service, parse_port_expression
from process_compose_orchestrator.modules.status.health_mapping import map_health, map_state, normalize_since


class StatusService:
    def __init__(self, lifecycle: InstanceLifecycleService, notifier: INotifier) -> None:
        self._lifecycle = lifecycle
        self._notifier = notifier

    def document(
        self,
        scope: Scope,
        services: tuple[Service, ...],
        patterns: list[ScopePattern],
        environ: Mapping[str, str],
    ) -> dict[str, Any]:
        """Declared services merged with whatever the live daemon runs (extension-declared ones included)."""
        self._lifecycle.require_binary()
        view = self._lifecycle.inspect(scope)
        if view.kind is InstanceKind.STALE:
            self._notifier.note(
                f"scope '{scope.name}': stale instance at {view.socket}; `winter service up` or `down` recovers it"
            )
        live = {p.name: p for p in view.processes}
        port_base = self._port_base(scope, environ)
        declared = {svc.name: svc for svc in services}
        entries: list[dict[str, Any]] = []
        for name in [*declared, *(n for n in live if n not in declared)]:
            if not matches(patterns, scope.name, name):
                continue
            svc = declared.get(name)
            proc = live.get(name)
            entries.append(
                {
                    "name": name,
                    "state": map_state(proc) if proc else "stopped",
                    "health": map_health(proc) if proc else "unknown",
                    "ports": self._ports(svc, port_base),
                    "handle": str(proc.pid) if proc and proc.pid else None,
                    "log_path": str(scope.log_path(name)),
                    "since": normalize_since(proc.start_time) if proc else None,
                }
            )
        return {"envs": [{"env": scope.name, "session": scope.name, "port_base": port_base, "services": entries}]}

    @staticmethod
    def _port_base(scope: Scope, environ: Mapping[str, str]) -> int | None:
        raw = environ.get("WINTER_WORKSPACE_PORT_BASE" if scope.is_workspace else "WINTER_PORT_BASE")
        try:
            return int(raw) if raw is not None else None
        except ValueError:
            return None

    @staticmethod
    def _ports(svc: Service | None, port_base: int | None) -> list[int]:
        if svc is None or svc.port is None:
            return []
        if isinstance(svc.port, int):
            return [svc.port]
        offset = parse_port_expression(svc.port)
        return [port_base + offset] if offset is not None and port_base is not None else []

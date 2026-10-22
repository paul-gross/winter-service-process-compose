"""Semantic validation of a parsed ``ServiceManifest``.

The reader raises on structural impossibility; the validator returns violations as data so the caller decides whether
they are fatal.
"""

from __future__ import annotations

import posixpath

from process_compose_orchestrator.modules.manifest.model import (
    Service,
    ServiceManifest,
    parse_port_expression,
)


class ManifestValidator:
    """Checks a manifest for duplicate names, bad values, and unresolvable or cyclic dependencies."""

    def validate(self, manifest: ServiceManifest) -> list[str]:
        """Return human-readable violations; an empty list means the manifest is clean."""
        violations: list[str] = []
        self._check_names(manifest, violations)
        for label, services in (("project", manifest.services), ("workspace", manifest.workspace_services)):
            self._check_values(services, violations)
            self._check_depends_on(services, label, violations)
        return violations

    @staticmethod
    def _check_names(manifest: ServiceManifest, violations: list[str]) -> None:
        seen: set[str] = set()
        for svc in (*manifest.services, *manifest.workspace_services):
            if svc.name in seen:
                violations.append(f"duplicate service name '{svc.name}'")
            seen.add(svc.name)

    @staticmethod
    def _check_values(services: tuple[Service, ...], violations: list[str]) -> None:
        for svc in services:
            if svc.cwd is not None:
                normalized = posixpath.normpath(svc.cwd)
                if posixpath.isabs(svc.cwd) or normalized == ".." or normalized.startswith("../"):
                    violations.append(f"service '{svc.name}': cwd '{svc.cwd}' must stay inside the scope root")
            if isinstance(svc.port, str) and parse_port_expression(svc.port) is None:
                violations.append(
                    f"service '{svc.name}': port expression '{svc.port}' must be 'WINTER_PORT_BASE + <int>'"
                )
            if isinstance(svc.port, int) and not 0 < svc.port < 65536:
                violations.append(f"service '{svc.name}': port {svc.port} is out of range")
            if svc.health is not None and svc.health.timeout is not None and svc.health.timeout <= 0:
                violations.append(f"service '{svc.name}': health.timeout must be positive")
            if svc.startup is not None and (svc.startup.retries < 0 or svc.startup.retry_delay < 0):
                violations.append(f"service '{svc.name}': startup.retries and startup.retry_delay must not be negative")
            if svc.restart is not None:
                if svc.restart.max_restarts is not None and svc.restart.max_restarts < 0:
                    violations.append(f"service '{svc.name}': restart.max_restarts must not be negative")
                if svc.restart.backoff_seconds is not None and svc.restart.backoff_seconds < 0:
                    violations.append(f"service '{svc.name}': restart.backoff_seconds must not be negative")

    def _check_depends_on(self, services: tuple[Service, ...], label: str, violations: list[str]) -> None:
        declared = {svc.name for svc in services}
        graph: dict[str, list[str]] = {}
        for svc in services:
            graph[svc.name] = []
            for dep in svc.depends_on:
                if dep == svc.name:
                    violations.append(f"service '{svc.name}': depends_on lists itself")
                elif dep not in declared:
                    violations.append(f"service '{svc.name}': depends_on '{dep}' matches no {label}-scope service")
                else:
                    graph[svc.name].append(dep)
        cycle = self._find_cycle(graph)
        if cycle is not None:
            violations.append("depends_on cycle: " + " -> ".join(cycle))

    @staticmethod
    def _find_cycle(graph: dict[str, list[str]]) -> list[str] | None:
        white, grey, black = 0, 1, 2
        color = dict.fromkeys(graph, white)
        path: list[str] = []

        def visit(node: str) -> list[str] | None:
            color[node] = grey
            path.append(node)
            for nxt in graph[node]:
                if color[nxt] == grey:
                    return [*path[path.index(nxt) :], nxt]
                if color[nxt] == white and (found := visit(nxt)) is not None:
                    return found
            path.pop()
            color[node] = black
            return None

        for start in graph:
            if color[start] == white and (found := visit(start)) is not None:
                return found
        return None

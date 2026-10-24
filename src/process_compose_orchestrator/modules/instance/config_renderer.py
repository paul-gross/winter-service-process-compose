"""Pure rendering of a scope's services into a process-compose JSON configuration.

No resolved scope value is ever written to the configuration: each process sources ``winter env <scope> --resolve``
in its own shell when it launches, so a ``restart`` sees the current env and ``project update`` sees only real
definition changes.
"""

from __future__ import annotations

import posixpath
import re
import shlex
from collections.abc import Collection, Mapping
from typing import Any
from urllib.parse import urlsplit

from process_compose_orchestrator.core.errors import ProcessComposeError
from process_compose_orchestrator.core.scope import Scope
from process_compose_orchestrator.modules.manifest.model import (
    Health,
    HealthType,
    RestartPolicy,
    Service,
)

_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_CONFIG_VERSION = "0.5"
_DEFAULT_HTTP_PORT = {"http": 80, "https": 443}
# process-compose terminates a process once its readiness probe fails this many times in a row, and its own default
# of 3 kills anything that takes longer than ~2s to start listening. Matching the provider's default `up` deadline at
# one probe a second lets a slow starter keep running for as long as `up` would wait on it.
_READINESS_FAILURE_THRESHOLD = 120


class ConfigRenderer:
    """Maps ``Service`` values onto process-compose process definitions."""

    def render(
        self,
        scope: Scope,
        services: tuple[Service, ...],
        enabled: Collection[str],
        environ: Mapping[str, str],
    ) -> dict[str, Any]:
        """Render *services*; those not in *enabled* are emitted ``disabled`` so they are defined but not started."""
        by_name = {svc.name: svc for svc in services}
        processes = {svc.name: self._process(scope, svc, svc.name in enabled, by_name, environ) for svc in services}
        return {"version": _CONFIG_VERSION, "disable_env_expansion": True, "processes": processes}

    def _process(
        self,
        scope: Scope,
        svc: Service,
        enabled: bool,
        by_name: Mapping[str, Service],
        environ: Mapping[str, str],
    ) -> dict[str, Any]:
        process: dict[str, Any] = {
            "command": self._command(scope, svc),
            "working_dir": str(scope.root / posixpath.normpath(svc.cwd)) if svc.cwd else str(scope.root),
            "log_location": str(scope.log_path(svc.name)),
            "log_configuration": {"flush_each_line": True, "add_timestamp": True},
        }
        if not enabled:
            process["disabled"] = True
        availability = self._availability(svc)
        if availability is not None:
            process["availability"] = availability
        if svc.health is not None:
            process["readiness_probe"] = self._probe(svc, svc.health, environ)
        if svc.depends_on:
            process["depends_on"] = {
                dep: {"condition": "process_healthy" if by_name[dep].health is not None else "process_started"}
                for dep in svc.depends_on
            }
        return process

    @staticmethod
    def _command(scope: Scope, svc: Service) -> str:
        parts = [f'__winter_env="$(winter env {shlex.quote(scope.name)} --resolve)" || exit 1', 'eval "$__winter_env"']
        for key, value in svc.env.items():
            parts.append(f'export {shlex.quote(key)}="{_double_quote_escape(value)}"')
        parts.append(svc.cmd)
        return "; ".join(parts)

    @staticmethod
    def _availability(svc: Service) -> dict[str, Any] | None:
        if svc.restart is not None:
            restart = svc.restart
            availability: dict[str, Any] = {"restart": restart.policy.value}
            if restart.backoff_seconds is not None:
                availability["backoff_seconds"] = _whole_or_float(restart.backoff_seconds)
            if restart.max_restarts is not None:
                availability["max_restarts"] = restart.max_restarts
            return availability
        if svc.startup is not None and svc.startup.retries > 0:
            return {
                "restart": RestartPolicy.ON_FAILURE.value,
                "backoff_seconds": _whole_or_float(svc.startup.retry_delay),
                "max_restarts": svc.startup.retries,
            }
        return None

    def _probe(self, svc: Service, health: Health, environ: Mapping[str, str]) -> dict[str, Any]:
        target = self._interpolate(svc.name, health.target, environ)
        probe: dict[str, Any] = {"period_seconds": 1, "failure_threshold": _READINESS_FAILURE_THRESHOLD}
        if health.timeout is not None:
            probe["timeout_seconds"] = _whole_or_float(health.timeout)
        if health.type is HealthType.URL:
            parts = urlsplit(target)
            scheme = parts.scheme or "http"
            path = parts.path or "/"
            probe["http_get"] = {
                "scheme": scheme,
                "host": parts.hostname or "localhost",
                "port": parts.port or _DEFAULT_HTTP_PORT.get(scheme, 80),
                "path": path + (f"?{parts.query}" if parts.query else ""),
            }
        else:
            probe["exec"] = {"command": target}
        return probe

    @staticmethod
    def _interpolate(service: str, text: str, environ: Mapping[str, str]) -> str:
        def sub(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in environ:
                raise ProcessComposeError(f"service '{service}': health target references unset variable ${{{name}}}")
            return environ[name]

        return _VAR_RE.sub(sub, text)


def _double_quote_escape(value: str) -> str:
    """Escape for a double-quoted shell string while leaving ``$`` references live."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`")


def _whole_or_float(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value

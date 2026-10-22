"""TOML adapter for ``IManifestReader``: parses ``config.toml`` into a ``ServiceManifest``.

All TOML parsing and file I/O for the workspace manifest is confined here. Keys this provider accepts but does not
use (``target``, ``log``) are dropped; constructs it cannot honor are refused with a message naming the provider.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path
from typing import Any

from process_compose_orchestrator.modules.manifest.errors import ManifestError, ManifestNotFoundError
from process_compose_orchestrator.modules.manifest.manifest_reader import IManifestReader
from process_compose_orchestrator.modules.manifest.model import (
    PROVIDER_LABEL,
    Health,
    HealthType,
    Restart,
    RestartPolicy,
    Service,
    ServiceManifest,
    StartupPolicy,
)

CONFIG_FILE = "config.toml"
_VALID_SCOPES = ("project", "workspace")
_WORKSPACE_SCOPE = "workspace"


class TomlManifestReader:
    """Reads ``<config_dir>/config.toml``; raises ``ManifestError`` on anything unreadable or refused."""

    def read(self, config_dir: Path) -> ServiceManifest:
        path = config_dir / CONFIG_FILE
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise ManifestNotFoundError(f"manifest not found: {path}") from None
        except OSError as exc:
            raise ManifestError(f"cannot read manifest {path}: {exc}") from exc
        try:
            doc = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ManifestError(f"malformed TOML in {path}: {exc}") from exc
        return self._build(doc)

    def _build(self, doc: dict[str, Any]) -> ServiceManifest:
        raw_services = doc.get("service", [])
        if not isinstance(raw_services, list):
            raise ManifestError("[[service]] must be an array of tables")
        project: list[Service] = []
        workspace: list[Service] = []
        for i, raw in enumerate(raw_services):
            if not isinstance(raw, dict):
                raise ManifestError(f"[[service]] entry #{i} must be a table")
            service, scope = self._parse_service(self._normalize_cmd_key(raw), i)
            (workspace if scope == _WORKSPACE_SCOPE else project).append(service)
        return ServiceManifest(services=tuple(project), workspace_services=tuple(workspace))

    @staticmethod
    def _normalize_cmd_key(entry: dict[str, Any]) -> dict[str, Any]:
        """Fold the deprecated ``command`` alias into ``cmd``; ``cmd`` wins when both are present."""
        if "command" not in entry:
            return entry
        result = dict(entry)
        alias = result.pop("command")
        if "cmd" not in result:
            sys.stderr.write(
                f"[{PROVIDER_LABEL}] deprecation: service '{entry.get('name', '<unknown>')}' uses 'command'; "
                "rename it to 'cmd'\n"
            )
            result["cmd"] = alias
        return result

    def _parse_service(self, raw: dict[str, Any], index: int) -> tuple[Service, str]:
        name = raw.get("name")
        if not name:
            raise ManifestError(f"[[service]] entry #{index} is missing required field 'name'")
        if not isinstance(name, str):
            raise ManifestError(f"[[service]] entry #{index}: name must be a string, got {type(name).__name__}")

        scope = raw.get("scope", "project")
        if scope not in _VALID_SCOPES:
            raise ManifestError(
                f"service '{name}': invalid scope {scope!r}; allowed values are "
                + ", ".join(repr(s) for s in _VALID_SCOPES)
            )

        cmd = raw.get("cmd", "")
        if not isinstance(cmd, str):
            raise ManifestError(f"service '{name}': cmd must be a string, got {type(cmd).__name__}")
        if not cmd.strip():
            raise ManifestError(
                f"service '{name}': {PROVIDER_LABEL} does not run interactive services — an empty cmd is refused; "
                "give the service a command or leave it to the tmux provider"
            )

        service = Service(
            name=name,
            cmd=cmd,
            cwd=self._parse_cwd(raw.get("cwd"), name),
            env=self._parse_env(raw.get("env"), name),
            port=self._parse_port(raw.get("port"), name),
            health=self._parse_health(raw.get("health"), name),
            depends_on=self._parse_depends_on(raw.get("depends_on"), name, scope),
            startup=self._parse_startup(raw.get("startup"), name),
            restart=self._parse_restart(raw.get("restart"), name),
        )
        return service, scope

    @staticmethod
    def _parse_cwd(raw: object, name: str) -> str | None:
        if raw is None:
            return None
        if not isinstance(raw, str):
            raise ManifestError(f"service '{name}': cwd must be a string, got {type(raw).__name__}")
        return raw[2:] if raw.startswith("./") else raw

    @staticmethod
    def _parse_env(raw: object, name: str) -> dict[str, str]:
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise ManifestError(f"service '{name}': 'env' must be a table, got {type(raw).__name__}")
        env: dict[str, str] = {}
        for key, value in raw.items():
            if not isinstance(value, str):
                raise ManifestError(f"service '{name}': env.{key} must be a string, got {type(value).__name__}")
            env[key] = value
        return env

    @staticmethod
    def _parse_port(raw: object, name: str) -> int | str | None:
        if raw is None:
            return None
        if isinstance(raw, bool) or not isinstance(raw, int | str):
            raise ManifestError(
                f"service '{name}': 'port' must be an integer or a string expression "
                f"(e.g. 'WINTER_PORT_BASE + 10'), got {type(raw).__name__}"
            )
        return raw

    @staticmethod
    def _parse_number(raw: object, label: str, name: str) -> float:
        if isinstance(raw, bool) or not isinstance(raw, int | float):
            raise ManifestError(f"service '{name}': {label} must be a number, got {type(raw).__name__}")
        return float(raw)

    @staticmethod
    def _parse_integer(raw: object, label: str, name: str) -> int:
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ManifestError(f"service '{name}': {label} must be an integer, got {type(raw).__name__}")
        return raw

    def _parse_health(self, raw: object, name: str) -> Health | None:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ManifestError(f"service '{name}': 'health' must be a table, got {type(raw).__name__}")
        type_raw = raw.get("type")
        if not isinstance(type_raw, str):
            raise ManifestError(f"service '{name}': health.type must be a string")
        target = raw.get("target")
        if not isinstance(target, str):
            raise ManifestError(f"service '{name}': health.target must be a string")
        try:
            health_type = HealthType(type_raw)
        except ValueError:
            if type_raw in ("log", "uptime"):
                raise ManifestError(
                    f"service '{name}': {PROVIDER_LABEL} does not support health.type {type_raw!r} — use 'url' or 'cmd'"
                ) from None
            allowed = ", ".join(repr(t.value) for t in HealthType)
            raise ManifestError(
                f"service '{name}': health.type value {type_raw!r} is not valid; allowed values are {allowed}"
            ) from None
        timeout_raw = raw.get("timeout")
        timeout = None if timeout_raw is None else self._parse_number(timeout_raw, "health.timeout", name)
        return Health(type=health_type, target=target, timeout=timeout)

    def _parse_startup(self, raw: object, name: str) -> StartupPolicy | None:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ManifestError(f"service '{name}': 'startup' must be a table, got {type(raw).__name__}")
        kwargs: dict[str, Any] = {}
        if (retries := raw.get("retries")) is not None:
            kwargs["retries"] = self._parse_integer(retries, "startup.retries", name)
        if (delay := raw.get("retry_delay")) is not None:
            kwargs["retry_delay"] = self._parse_number(delay, "startup.retry_delay", name)
        return StartupPolicy(**kwargs)

    def _parse_restart(self, raw: object, name: str) -> Restart | None:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ManifestError(f"service '{name}': 'restart' must be a table, got {type(raw).__name__}")
        policy_raw = raw.get("policy")
        if not isinstance(policy_raw, str):
            raise ManifestError(f"service '{name}': restart.policy must be a string")
        try:
            policy = RestartPolicy(policy_raw)
        except ValueError:
            allowed = ", ".join(repr(p.value) for p in RestartPolicy)
            raise ManifestError(
                f"service '{name}': restart.policy value {policy_raw!r} is not valid; allowed values are {allowed}"
            ) from None
        backoff_raw = raw.get("backoff_seconds")
        max_raw = raw.get("max_restarts")
        return Restart(
            policy=policy,
            backoff_seconds=None
            if backoff_raw is None
            else self._parse_number(backoff_raw, "restart.backoff_seconds", name),
            max_restarts=None if max_raw is None else self._parse_integer(max_raw, "restart.max_restarts", name),
        )

    @staticmethod
    def _parse_depends_on(raw: object, name: str, scope: str) -> tuple[str, ...]:
        """Return same-scope dependency names; a reference into any other scope is refused."""
        if raw is None:
            return ()
        if not isinstance(raw, list):
            raise ManifestError(f"service '{name}': 'depends_on' must be a list of strings, got {type(raw).__name__}")
        names: list[str] = []
        for item in raw:
            if not isinstance(item, str):
                raise ManifestError(
                    f"service '{name}': 'depends_on' entries must be strings, got {type(item).__name__}"
                )
            if "/" in item:
                qualifier, _, bare = item.partition("/")
                if scope == _WORKSPACE_SCOPE and qualifier == _WORKSPACE_SCOPE and bare:
                    names.append(bare)
                    continue
                raise ManifestError(
                    f"service '{name}': {PROVIDER_LABEL} does not support cross-scope depends_on ({item!r}) — "
                    "reference a service of the same scope by bare name"
                )
            names.append(item)
        return tuple(names)


def _conforms_toml_manifest_reader(x: TomlManifestReader) -> IManifestReader:
    return x

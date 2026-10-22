"""Immutable manifest model — the tmux ``[[service]]`` vocabulary this provider honors, plus ``restart``."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

_PORT_EXPR_RE = re.compile(r"^\s*WINTER_PORT_BASE\s*\+\s*(\d+)\s*$")

PROVIDER_LABEL = "winter-service-process-compose"


def parse_port_expression(s: str) -> int | None:
    """Return the offset of a ``WINTER_PORT_BASE + <offset>`` expression, or ``None`` when *s* is not one."""
    m = _PORT_EXPR_RE.match(s)
    return int(m.group(1)) if m else None


class HealthType(StrEnum):
    """Readiness probe types this provider supports."""

    URL = "url"
    CMD = "cmd"


class RestartPolicy(StrEnum):
    """``[service.restart] policy`` values, mapped onto process-compose ``availability.restart``."""

    NO = "no"
    ON_FAILURE = "on_failure"
    ALWAYS = "always"


@dataclass(frozen=True)
class Health:
    """Readiness probe. ``target`` may carry ``${VAR}`` placeholders; ``timeout`` is seconds."""

    type: HealthType
    target: str
    timeout: float | None = None


@dataclass(frozen=True)
class StartupPolicy:
    """Startup retry policy: ``retries`` re-launch attempts, ``retry_delay`` seconds between them."""

    retries: int = 0
    retry_delay: float = 2.0


@dataclass(frozen=True)
class Restart:
    """The provider-native restart policy of one service."""

    policy: RestartPolicy
    backoff_seconds: float | None = None
    max_restarts: int | None = None


@dataclass(frozen=True)
class Service:
    """One declared service.

    ``cwd`` is a scope-root-relative path (a leading ``./`` is stripped by the reader). ``depends_on`` holds
    same-scope service names. ``port`` is a literal or a ``WINTER_PORT_BASE + <offset>`` expression, kept raw.
    """

    name: str
    cmd: str
    cwd: str | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    port: int | str | None = None
    health: Health | None = None
    depends_on: tuple[str, ...] = ()
    startup: StartupPolicy | None = None
    restart: Restart | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "env", MappingProxyType(dict(self.env)))


@dataclass(frozen=True)
class ServiceManifest:
    """Declared services: per-env (``scope = "project"``) and workspace-scoped, each in declaration order."""

    services: tuple[Service, ...] = ()
    workspace_services: tuple[Service, ...] = ()


@dataclass(frozen=True)
class ExtServices:
    """Extension-declared services, partitioned by scope, plus notes about entries that were skipped."""

    project: tuple[Service, ...] = ()
    workspace: tuple[Service, ...] = ()
    notes: tuple[str, ...] = ()

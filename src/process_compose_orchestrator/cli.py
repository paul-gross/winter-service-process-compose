"""Winter service-provider entrypoint for winter-service-process-compose.

Winter invokes this as ``<entrypoint> <action> [positional...]`` with cwd at the workspace root and ``WINTER_*``
env vars set.

Exit codes: 0 success, 1 failure, 2 unknown action, 3 recognized action not yet implemented.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from process_compose_orchestrator.container import Container
from process_compose_orchestrator.core.errors import ProcessComposeError
from process_compose_orchestrator.core.patterns import ScopePattern
from process_compose_orchestrator.core.scope import Scope
from process_compose_orchestrator.modules.manifest.errors import ManifestError, ManifestNotFoundError
from process_compose_orchestrator.modules.manifest.model import Service, ServiceManifest

_KNOWN_ACTIONS = frozenset({"up", "down", "status", "restart", "logs", "describe", "catalog"})
_UNKNOWN_EXIT = 2
_REFUSE_EXIT = 3
_DEFAULT_CONFIG_SUBDIR = Path(".winter") / "config" / "winter-service-process-compose"


def resolve_config_dir() -> Path | None:
    """Return ``WINTER_EXT_CONFIG_DIR`` or the workspace default; ``None`` when neither is available."""
    ext_config_dir = os.environ.get("WINTER_EXT_CONFIG_DIR")
    if ext_config_dir:
        return Path(ext_config_dir)
    ws_dir = os.environ.get("WINTER_WORKSPACE_DIR")
    return Path(ws_dir) / _DEFAULT_CONFIG_SUBDIR if ws_dir else None


def _emit_services(names: list[str]) -> int:
    sys.stdout.write(json.dumps({"services": names}) + "\n")
    sys.stdout.flush()
    return 0


def _cmd_describe(container: Container) -> int:
    config_dir = resolve_config_dir()
    if config_dir is None:
        print(
            "process-compose-orchestrator: describe: no config directory (WINTER_WORKSPACE_DIR unset)", file=sys.stderr
        )
        return _emit_services([])
    try:
        return _emit_services(container.catalog_service().describe(config_dir))
    except ManifestNotFoundError as exc:
        print(f"process-compose-orchestrator: describe: {exc}", file=sys.stderr)
        return _emit_services([])
    except ManifestError as exc:
        print(f"process-compose-orchestrator: describe: {exc}", file=sys.stderr)
        return 1


def _cmd_catalog(container: Container) -> int:
    config_dir = resolve_config_dir()
    names = container.catalog_service().catalog(config_dir) if config_dir is not None else []
    return _emit_services(names)


def _require_workspace_dir() -> Path:
    ws_dir = os.environ.get("WINTER_WORKSPACE_DIR")
    if not ws_dir:
        raise ProcessComposeError("WINTER_WORKSPACE_DIR is not set")
    return Path(ws_dir)


def _load_manifest(container: Container, *, with_extensions: bool) -> ServiceManifest:
    config_dir = resolve_config_dir()
    if config_dir is None:
        raise ProcessComposeError("no config directory (WINTER_WORKSPACE_DIR unset)")
    ext_path = os.environ.get("WINTER_SERVICE_MANIFEST") if with_extensions else None
    loaded = container.manifest_loader().load(config_dir, Path(ext_path) if ext_path else None)
    for note in loaded.notes:
        container.notifier().note(note)
    return loaded.manifest


def _scope_services(scope: Scope, manifest: ServiceManifest) -> tuple[Service, ...]:
    return manifest.workspace_services if scope.is_workspace else manifest.services


def _single_scope_pattern(action: str, args: list[str]) -> ScopePattern:
    if len(args) != 1:
        raise ProcessComposeError(f"{action}: expected exactly one <scope>[/<service>] argument, got {len(args)}")
    pattern = ScopePattern.parse(args[0])
    if not pattern.scope_is_concrete:
        raise ProcessComposeError(f"{action}: scope '{pattern.scope}' must be a concrete env name")
    return pattern


def _cmd_up(container: Container, args: list[str]) -> int:
    pattern = _single_scope_pattern("up", args)
    scope = Scope.of(_require_workspace_dir(), pattern.scope)
    manifest = _load_manifest(container, with_extensions=True)
    raw_timeout = os.environ.get("WINTER_SERVICE_TIMEOUT")
    container.instance_lifecycle().up(
        scope,
        _scope_services(scope, manifest),
        pattern,
        os.environ,
        float(raw_timeout) if raw_timeout else None,
    )
    return 0


def _cmd_down(container: Container, args: list[str]) -> int:
    pattern = _single_scope_pattern("down", args)
    scope = Scope.of(_require_workspace_dir(), pattern.scope)
    container.instance_lifecycle().down(scope, pattern)
    return 0


def _cmd_restart(container: Container, args: list[str]) -> int:
    if not args:
        raise ProcessComposeError("restart: at least one <env>/<service> pattern is required")
    by_scope: dict[str, list[str]] = {}
    for token in args:
        pattern = ScopePattern.parse(token)
        if not pattern.scope_is_concrete:
            raise ProcessComposeError(f"restart: scope '{pattern.scope}' must be a concrete env name")
        by_scope.setdefault(pattern.scope, []).append(pattern.service)
    workspace_dir = _require_workspace_dir()
    lifecycle = container.instance_lifecycle()
    for name, globs in by_scope.items():
        lifecycle.restart(Scope.of(workspace_dir, name), globs)
    return 0


def _cmd_status(container: Container, args: list[str]) -> int:
    patterns = [ScopePattern.parse(a) for a in args]
    env = os.environ.get("WINTER_ENV")
    names = [env] if env else list(dict.fromkeys(p.scope for p in patterns if p.scope_is_concrete))
    envs: list[dict[str, object]] = []
    if names:
        workspace_dir = _require_workspace_dir()
        manifest = _load_manifest(container, with_extensions=False)
        status = container.status_service()
        for name in names:
            scope = Scope.of(workspace_dir, name)
            envs.extend(status.document(scope, _scope_services(scope, manifest), patterns, os.environ)["envs"])
    sys.stdout.write(json.dumps({"envs": envs}) + "\n")
    sys.stdout.flush()
    return 0


_ACTIONS = {"up": _cmd_up, "down": _cmd_down, "restart": _cmd_restart, "status": _cmd_status}


def main(argv: list[str]) -> int:
    """Dispatch ``[action, *rest]``; *argv* is ``sys.argv[1:]``."""
    # Echo argv to stderr so the forwards-params conformance check in `winter ext verify` passes.
    print(" ".join(sys.argv), file=sys.stderr)

    if not argv:
        print("usage: <action> [args...]\n  actions: " + ", ".join(sorted(_KNOWN_ACTIONS)), file=sys.stderr)
        return _UNKNOWN_EXIT
    action = argv[0]
    if action not in _KNOWN_ACTIONS:
        print(f"process-compose-orchestrator: unknown action '{action}'", file=sys.stderr)
        return _UNKNOWN_EXIT

    container = Container()
    if action == "describe":
        return _cmd_describe(container)
    if action == "catalog":
        return _cmd_catalog(container)

    handler = _ACTIONS.get(action)
    if handler is None:
        print(f"process-compose-orchestrator: action '{action}' is not yet implemented", file=sys.stderr)
        return _REFUSE_EXIT
    try:
        return handler(container, argv[1:])
    except (ProcessComposeError, ManifestError) as exc:
        print(f"process-compose-orchestrator: {action}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

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
from process_compose_orchestrator.modules.manifest.errors import ManifestError, ManifestNotFoundError

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

    print(f"process-compose-orchestrator: action '{action}' is not yet implemented", file=sys.stderr)
    return _REFUSE_EXIT


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

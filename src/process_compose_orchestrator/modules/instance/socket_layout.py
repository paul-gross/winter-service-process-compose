"""Pure derivation of a scope's control-socket path, with the sun_path fallback."""

from __future__ import annotations

import hashlib
from pathlib import Path

from process_compose_orchestrator.core.errors import ProcessComposeError
from process_compose_orchestrator.core.scope import Scope

# sun_path holds 108 bytes including the trailing NUL.
MAX_SOCKET_PATH_BYTES = 107


class SocketLayout:
    """Chooses ``<state-dir>/pc.sock``, or a short deterministic path when that would not fit in sun_path.

    Every action recomputes the choice from the scope alone, so no state is needed to find an instance.
    """

    def __init__(self, uid: int, runtime_dir: Path) -> None:
        self._uid = uid
        self._runtime_dir = runtime_dir

    def socket_path(self, scope: Scope) -> Path:
        primary = scope.state_dir / "pc.sock"
        if len(str(primary).encode()) <= MAX_SOCKET_PATH_BYTES:
            return primary
        digest = hashlib.sha256(str(scope.root).encode()).hexdigest()[:16]
        fallback = self._runtime_dir / f"winter-pc-{self._uid}" / f"{digest}.sock"
        if len(str(fallback).encode()) > MAX_SOCKET_PATH_BYTES:
            raise ProcessComposeError(
                f"scope '{scope.name}': neither {primary} nor the fallback {fallback} fits in a unix socket path "
                f"({MAX_SOCKET_PATH_BYTES} bytes); set XDG_RUNTIME_DIR to a shorter directory"
            )
        return fallback

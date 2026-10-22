"""``IInstanceStateStore`` over files in the scope's state directory, locked with ``flock``."""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path

from process_compose_orchestrator.core.scope import Scope
from process_compose_orchestrator.modules.instance.instance_state import IInstanceStateStore, InstanceState


class FileInstanceStateStore:
    def read(self, scope: Scope) -> InstanceState | None:
        try:
            data = json.loads(scope.state_path.read_text())
            return InstanceState(sid=int(data["sid"]), socket=str(data["socket"]))
        except (OSError, ValueError, KeyError):
            return None

    def write(self, scope: Scope, state: InstanceState) -> None:
        scope.state_dir.mkdir(parents=True, exist_ok=True)
        tmp = scope.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"sid": state.sid, "socket": state.socket}))
        os.replace(tmp, scope.state_path)

    def clear(self, scope: Scope) -> None:
        scope.state_path.unlink(missing_ok=True)

    def lock(self, scope: Scope) -> AbstractContextManager[None]:
        return self._locked(scope)

    @contextmanager
    def _locked(self, scope: Scope) -> Iterator[None]:
        scope.state_dir.mkdir(parents=True, exist_ok=True)
        with scope.lock_path.open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def remove_socket(self, socket: Path) -> None:
        socket.unlink(missing_ok=True)

    def socket_exists(self, socket: Path) -> bool:
        return socket.exists()


def _conforms_file_instance_state_store(x: FileInstanceStateStore) -> IInstanceStateStore:
    return x

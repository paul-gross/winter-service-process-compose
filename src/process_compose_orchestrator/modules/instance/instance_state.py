"""Protocol seam over a scope's persisted instance state and its advisory lock."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from process_compose_orchestrator.core.scope import Scope


@dataclass(frozen=True)
class InstanceState:
    """What a later action needs to recover an instance whose daemon died."""

    sid: int
    socket: str


class IInstanceStateStore(Protocol):
    def read(self, scope: Scope) -> InstanceState | None: ...

    def write(self, scope: Scope, state: InstanceState) -> None: ...

    def clear(self, scope: Scope) -> None: ...

    def lock(self, scope: Scope) -> AbstractContextManager[None]:
        """Hold the scope's exclusive advisory lock for the duration of the ``with`` block."""
        ...

    def remove_socket(self, socket: Path) -> None: ...

    def socket_exists(self, socket: Path) -> bool: ...

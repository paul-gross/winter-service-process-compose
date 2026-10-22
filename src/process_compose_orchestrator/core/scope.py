"""The ``Scope`` domain type: one process-compose instance's identity and on-disk layout."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

WORKSPACE_SCOPE = "workspace"
STATE_SUBDIR = Path(".winter") / "process-compose"


@dataclass(frozen=True)
class Scope:
    """A feature env or the workspace, rooted at *root*.

    Identity derives from the workspace directory and the scope name only — never from ``WINTER_ENV`` or
    ``WINTER_SERVICE_PREFIX``, which can be absent on ``down``.
    """

    name: str
    root: Path

    @classmethod
    def of(cls, workspace_dir: Path, name: str) -> Scope:
        """Build the scope called *name* inside *workspace_dir*."""
        return cls(name=name, root=workspace_dir if name == WORKSPACE_SCOPE else workspace_dir / name)

    @property
    def is_workspace(self) -> bool:
        return self.name == WORKSPACE_SCOPE

    @property
    def state_dir(self) -> Path:
        return self.root / STATE_SUBDIR

    @property
    def log_dir(self) -> Path:
        return self.state_dir / "logs"

    @property
    def config_path(self) -> Path:
        return self.state_dir / "config.json"

    @property
    def daemon_log_path(self) -> Path:
        return self.state_dir / "daemon.log"

    @property
    def state_path(self) -> Path:
        return self.state_dir / "state.json"

    @property
    def lock_path(self) -> Path:
        return self.state_dir / "lock"

    def log_path(self, service: str) -> Path:
        return self.log_dir / f"{service}.log"

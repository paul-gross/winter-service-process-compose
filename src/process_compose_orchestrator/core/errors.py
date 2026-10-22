"""Provider-wide error type and the factory that builds it from subprocess results."""

from __future__ import annotations

import subprocess
from pathlib import Path


class ProcessComposeError(Exception):
    """A failed interaction with the process-compose binary or a scope's instance.

    The structured fields carry what the failing call knew; the message stays a
    short human sentence.
    """

    def __init__(
        self,
        message: str,
        *,
        cmd_args: tuple[str, ...] = (),
        exit_code: int | None = None,
        stderr: str = "",
        cwd: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.cmd_args = cmd_args
        self.exit_code = exit_code
        self.stderr = stderr
        self.cwd = cwd


class ProcessComposeErrorFactory:
    """Builds ``ProcessComposeError`` values; injected so adapters never construct errors directly."""

    def from_subprocess(
        self,
        completed: subprocess.CompletedProcess[str],
        message: str,
        *,
        cwd: Path | None = None,
    ) -> ProcessComposeError:
        args = completed.args
        cmd_args = tuple(str(a) for a in args) if isinstance(args, list | tuple) else (str(args),)
        return ProcessComposeError(
            message,
            cmd_args=cmd_args,
            exit_code=completed.returncode,
            stderr=completed.stderr or "",
            cwd=cwd,
        )

    def from_os_error(
        self, exc: OSError, message: str, *, cmd_args: tuple[str, ...], cwd: Path | None = None
    ) -> ProcessComposeError:
        return ProcessComposeError(f"{message}: {exc}", cmd_args=cmd_args, stderr=str(exc), cwd=cwd)

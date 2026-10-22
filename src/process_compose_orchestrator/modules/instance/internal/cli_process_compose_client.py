"""``IProcessComposeClient`` over the ``process-compose`` CLI.

Every subprocess call in the provider's control path lives here. Calls use list-form argv with ``check=False``,
always pass an explicit ``-u`` socket (the default socket and log paths are shared per user), and drop the binary's
``"level":"debug"`` stderr noise before forwarding what is left.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from process_compose_orchestrator.core.errors import ProcessComposeError, ProcessComposeErrorFactory
from process_compose_orchestrator.modules.instance.clock import IClock
from process_compose_orchestrator.modules.instance.process_compose_client import (
    IProcessComposeClient,
    ProcessInfo,
)

BINARY = "process-compose"
_LAUNCH_WAIT_SECONDS = 15.0
_LAUNCH_POLL_SECONDS = 0.1
_DAEMON_LOG_TAIL_LINES = 20


class CliProcessComposeClient:
    def __init__(self, errors: ProcessComposeErrorFactory, clock: IClock) -> None:
        self._errors = errors
        self._clock = clock

    def is_available(self) -> bool:
        return shutil.which(BINARY) is not None

    def launch(self, socket: Path, config: Path, daemon_log: Path) -> None:
        socket.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        result = self._run(
            ["up", "-D", "-t=false", "-U", "-u", str(socket), "-f", str(config), "-L", str(daemon_log)],
        )
        if result.returncode != 0:
            raise self._errors.from_subprocess(result, self._launch_message(daemon_log, "process-compose up failed"))
        deadline = self._clock.monotonic() + _LAUNCH_WAIT_SECONDS
        while self._clock.monotonic() < deadline:
            if self.list_processes(socket) is not None:
                return
            self._clock.sleep(_LAUNCH_POLL_SECONDS)
        raise ProcessComposeError(self._launch_message(daemon_log, "process-compose daemon did not come up"))

    def update(self, socket: Path, config: Path) -> None:
        self._must(["-U", "-u", str(socket), "project", "update", "-f", str(config)], "project update failed")

    def down(self, socket: Path) -> None:
        self._must(["-U", "-u", str(socket), "down"], "process-compose down failed")

    def list_processes(self, socket: Path) -> list[ProcessInfo] | None:
        result = self._run(["-U", "-u", str(socket), "process", "list", "-o", "json"])
        if result.returncode != 0:
            return None
        try:
            raw = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            return None
        return [
            ProcessInfo(
                name=str(item["name"]),
                status=str(item.get("status", "")),
                is_ready=str(item.get("is_ready", "-")),
                has_ready_probe=bool(item.get("has_ready_probe", False)),
                pid=int(item.get("pid", 0) or 0),
                restarts=int(item.get("restarts", 0) or 0),
                start_time=item.get("process_start_time") or None,
            )
            for item in raw
        ]

    def start_process(self, socket: Path, name: str) -> None:
        self._must(["-U", "-u", str(socket), "process", "start", name], f"could not start '{name}'")

    def stop_process(self, socket: Path, name: str) -> None:
        self._must(["-U", "-u", str(socket), "process", "stop", name], f"could not stop '{name}'")

    def restart_process(self, socket: Path, name: str) -> None:
        self._must(["-U", "-u", str(socket), "process", "restart", name], f"could not restart '{name}'")

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run([BINARY, *args], capture_output=True, text=True, check=False)
        except OSError as exc:
            raise self._errors.from_os_error(exc, "could not run process-compose", cmd_args=(BINARY, *args)) from exc

    def _must(self, args: list[str], message: str) -> None:
        result = self._run(args)
        self._forward_stderr(result.stderr)
        if result.returncode != 0:
            raise self._errors.from_subprocess(result, f"{message} (exit {result.returncode})")

    @staticmethod
    def _forward_stderr(stderr: str) -> None:
        for line in stderr.splitlines():
            if '"level":"debug"' not in line and line.strip():
                print(line, file=sys.stderr)

    @staticmethod
    def _launch_message(daemon_log: Path, headline: str) -> str:
        try:
            tail = daemon_log.read_text(errors="replace").splitlines()[-_DAEMON_LOG_TAIL_LINES:]
        except OSError:
            tail = []
        return f"{headline}; daemon log {daemon_log}:\n" + "\n".join(tail) if tail else headline


def _conforms_cli_process_compose_client(x: CliProcessComposeClient) -> IProcessComposeClient:
    return x

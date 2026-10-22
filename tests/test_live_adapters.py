"""Adapters against the real binary and /proc; skipped when ``process-compose`` is absent."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from process_compose_orchestrator.core.errors import ProcessComposeErrorFactory
from process_compose_orchestrator.modules.instance.internal.cli_process_compose_client import CliProcessComposeClient
from process_compose_orchestrator.modules.instance.internal.proc_session_reaper import ProcSessionReaper
from process_compose_orchestrator.modules.instance.internal.system_clock import SystemClock

pytestmark = pytest.mark.skipif(shutil.which("process-compose") is None, reason="process-compose not installed")


def test_launch_list_update_down_roundtrip() -> None:
    clock = SystemClock()
    client = CliProcessComposeClient(ProcessComposeErrorFactory(), clock)
    reaper = ProcSessionReaper(clock)
    with tempfile.TemporaryDirectory(prefix="pc") as tmp:
        root = Path(tmp)
        config = root / "c.json"
        config.write_text(
            json.dumps({"version": "0.5", "processes": {"a": {"command": "sleep 300", "disabled": True}}})
        )
        socket = root / "pc.sock"
        client.launch(socket, config, root / "d.log")
        try:
            sid = reaper.find_daemon_sid(socket)
            assert sid is not None and reaper.pid_alive(sid)
            assert [p.status for p in client.list_processes(socket) or []] == ["Disabled"]
            config.write_text(json.dumps({"version": "0.5", "processes": {"a": {"command": "sleep 300"}}}))
            client.update(socket, config)
            (proc,) = client.list_processes(socket) or []
            assert proc.status == "Running" and proc.pid > 0 and proc.start_time
        finally:
            client.down(socket)
        assert client.list_processes(socket) is None
        assert not os.path.exists(socket)

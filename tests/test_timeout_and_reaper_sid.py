from __future__ import annotations

from pathlib import Path

import pytest

from process_compose_orchestrator import cli
from process_compose_orchestrator.core.errors import ProcessComposeError
from process_compose_orchestrator.modules.instance.internal.proc_session_reaper import ProcSessionReaper
from tests.fakes import FakeClock


def _fake_proc(root: Path, pid: int, sid: int, socket: Path) -> None:
    d = root / str(pid)
    d.mkdir(parents=True)
    (d / "cmdline").write_bytes(b"\0".join([b"/usr/bin/process-compose", b"-u", str(socket).encode()]) + b"\0")
    (d / "stat").write_text(f"{pid} (process-compose) S 1 {pid} {sid} 0 0\n")


def test_non_numeric_timeout_is_a_provider_error() -> None:
    with pytest.raises(ProcessComposeError, match="WINTER_SERVICE_TIMEOUT"):
        cli._parse_timeout("abc")
    assert cli._parse_timeout("2.5") == 2.5
    assert cli._parse_timeout(None) is None


def test_daemon_sid_requires_daemon_to_lead_its_session(tmp_path: Path) -> None:
    sock = tmp_path / "pc.sock"
    leader = tmp_path / "proc_a"
    _fake_proc(leader, 100, 100, sock)
    assert ProcSessionReaper(FakeClock(), leader).find_daemon_sid(sock) == 100

    shared = tmp_path / "proc_b"
    _fake_proc(shared, 200, 50, sock)
    assert ProcSessionReaper(FakeClock(), shared).find_daemon_sid(sock) is None

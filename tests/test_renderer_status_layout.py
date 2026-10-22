from __future__ import annotations

from pathlib import Path

import pytest

from process_compose_orchestrator.core.errors import ProcessComposeError
from process_compose_orchestrator.core.patterns import ScopePattern, matches
from process_compose_orchestrator.core.scope import Scope
from process_compose_orchestrator.modules.instance.config_renderer import ConfigRenderer
from process_compose_orchestrator.modules.instance.lifecycle_service import InstanceLifecycleService
from process_compose_orchestrator.modules.instance.socket_layout import MAX_SOCKET_PATH_BYTES, SocketLayout
from process_compose_orchestrator.modules.manifest.model import (
    Health,
    HealthType,
    Restart,
    RestartPolicy,
    Service,
    StartupPolicy,
)
from process_compose_orchestrator.modules.status.health_mapping import map_health, map_state, normalize_since
from process_compose_orchestrator.modules.status.status_service import StatusService
from tests.fakes import FakeClient, FakeClock, FakeNotifier, FakeReaper, FakeStateStore, proc

SCOPE = Scope.of(Path("/ws"), "e1")


def _render(*services: Service, enabled: set[str] | None = None, environ: dict[str, str] | None = None) -> dict:
    names = {s.name for s in services} if enabled is None else enabled
    return ConfigRenderer().render(SCOPE, services, names, environ or {})["processes"]


def test_renderer_sets_expansion_off_and_flushes_logs() -> None:
    config = ConfigRenderer().render(SCOPE, (Service(name="a", cmd="echo $HOME"),), {"a"}, {})
    assert config["disable_env_expansion"] is True
    a = config["processes"]["a"]
    assert a["command"].endswith("; echo $HOME")
    assert "winter env e1 --resolve" in a["command"]
    assert a["log_location"] == "/ws/e1/.winter/process-compose/logs/a.log"
    assert a["log_configuration"] == {"flush_each_line": True, "add_timestamp": True}
    assert a["working_dir"] == "/ws/e1"


def test_renderer_cwd_env_and_disabled() -> None:
    svc = Service(name="a", cmd="x", cwd="sub/dir", env={"K": 'v"1 $REF'})
    a = _render(svc, enabled=set())["a"]
    assert a["working_dir"] == "/ws/e1/sub/dir"
    assert a["disabled"] is True
    assert 'export K="v\\"1 $REF"' in a["command"]


def test_renderer_workspace_scope_root() -> None:
    ws = Scope.of(Path("/ws"), "workspace")
    a = ConfigRenderer().render(ws, (Service(name="a", cmd="x"),), {"a"}, {})["processes"]["a"]
    assert a["working_dir"] == "/ws"


def test_renderer_health_mapping_and_interpolation() -> None:
    url = Service(name="u", cmd="x", health=Health(HealthType.URL, "http://localhost:${P}/api/h?x=1", 3))
    cmd = Service(name="c", cmd="x", health=Health(HealthType.CMD, "test -f ${F}"))
    out = _render(url, cmd, environ={"P": "4251", "F": "/tmp/f"})
    assert out["u"]["readiness_probe"]["http_get"] == {
        "scheme": "http", "host": "localhost", "port": 4251, "path": "/api/h?x=1",
    }  # fmt: skip
    assert out["u"]["readiness_probe"]["timeout_seconds"] == 3
    assert out["c"]["readiness_probe"]["exec"] == {"command": "test -f /tmp/f"}


def test_renderer_unset_health_variable_is_an_error() -> None:
    svc = Service(name="u", cmd="x", health=Health(HealthType.URL, "http://localhost:${P}/"))
    with pytest.raises(ProcessComposeError, match="unset variable"):
        _render(svc)


def test_renderer_restart_and_startup_mapping() -> None:
    native = Service(name="n", cmd="x", restart=Restart(RestartPolicy.ALWAYS, 1.5, 4), startup=StartupPolicy(9, 9))
    retry = Service(name="r", cmd="x", startup=StartupPolicy(3, 2.0))
    plain = Service(name="p", cmd="x")
    out = _render(native, retry, plain)
    assert out["n"]["availability"] == {"restart": "always", "backoff_seconds": 1.5, "max_restarts": 4}
    assert out["r"]["availability"] == {"restart": "on_failure", "backoff_seconds": 2, "max_restarts": 3}
    assert "availability" not in out["p"]


def test_renderer_depends_on_condition_follows_dependency_health() -> None:
    db = Service(name="db", cmd="x", health=Health(HealthType.CMD, "true"))
    plain = Service(name="plain", cmd="x")
    app = Service(name="app", cmd="x", depends_on=("db", "plain"))
    deps = _render(db, plain, app)["app"]["depends_on"]
    assert deps == {"db": {"condition": "process_healthy"}, "plain": {"condition": "process_started"}}


def test_socket_layout_primary_and_fallback() -> None:
    layout = SocketLayout(1000, Path("/run/user/1000"))
    short = Scope.of(Path("/ws"), "e1")
    assert layout.socket_path(short) == Path("/ws/e1/.winter/process-compose/pc.sock")
    long = Scope.of(Path("/w" + "x" * 120), "e1")
    fallback = layout.socket_path(long)
    assert fallback.parent == Path("/run/user/1000/winter-pc-1000")
    assert len(str(fallback).encode()) <= MAX_SOCKET_PATH_BYTES
    assert layout.socket_path(long) == fallback


def test_socket_layout_refuses_when_fallback_is_too_long() -> None:
    layout = SocketLayout(1000, Path("/r" + "y" * 120))
    with pytest.raises(ProcessComposeError, match="XDG_RUNTIME_DIR"):
        layout.socket_path(Scope.of(Path("/w" + "x" * 120), "e1"))


def test_state_and_health_mapping() -> None:
    assert map_state(proc("a", "Running")) == "running"
    for terminal in ("Completed", "Error", "Skipped", "Disabled"):
        assert map_state(proc("a", terminal)) == "stopped"
    assert map_state(proc("a", "Pending")) == "unknown"
    assert map_health(proc("a", ready="Ready", probe=True)) == "healthy"
    assert map_health(proc("a", "Pending", ready="Not Ready", probe=True)) == "unhealthy"
    assert map_health(proc("a")) == "unknown"


def test_normalize_since() -> None:
    assert normalize_since("2026-10-22T06:55:11.130612088-05:00") == "2026-10-22T11:55:11.130612Z"
    assert normalize_since("2026-10-22T06:55:11Z") == "2026-10-22T06:55:11.000000Z"
    assert normalize_since("0001-01-01T00:00:00Z") is None
    assert normalize_since(None) is None
    assert normalize_since("garbage") is None


def test_pattern_parsing_and_matching() -> None:
    assert ScopePattern.parse("e1") == ScopePattern("e1", "*")
    assert ScopePattern.parse("e1/a*").covers_whole_scope is False
    assert not ScopePattern.parse("*/api").scope_is_concrete
    assert matches([ScopePattern.parse("*/api")], "e1", "api")
    assert not matches([ScopePattern.parse("e2")], "e1", "api")
    assert matches([], "e1", "api")


def _status(client: FakeClient) -> StatusService:
    lifecycle = InstanceLifecycleService(
        client, FakeReaper(), FakeStateStore(), SocketLayout(1, Path("/run")), ConfigRenderer(), FakeClock(),
        FakeNotifier(),
    )  # fmt: skip
    return StatusService(lifecycle, FakeNotifier())


def test_status_document_merges_declared_and_live_extension_services(tmp_path: Path) -> None:
    scope = Scope.of(tmp_path, "e1")
    socket = SocketLayout(1, Path("/run")).socket_path(scope)
    socket.parent.mkdir(parents=True)
    socket.touch()
    client = FakeClient()
    client.alive[socket] = [proc("api", ready="Ready", probe=True, pid=11), proc("ext", pid=12)]
    declared = (Service(name="api", cmd="x", port="WINTER_PORT_BASE + 2"), Service(name="idle", cmd="x", port=99))
    doc = _status(client).document(scope, declared, [], {"WINTER_PORT_BASE": "4240"})
    env = doc["envs"][0]
    assert env["port_base"] == 4240
    by_name = {s["name"]: s for s in env["services"]}
    assert by_name["api"]["health"] == "healthy"
    assert by_name["api"]["ports"] == [4242]
    assert by_name["api"]["handle"] == "11"
    assert by_name["ext"]["state"] == "running"
    assert by_name["idle"] == {
        "name": "idle", "state": "stopped", "health": "unknown", "ports": [99], "handle": None,
        "log_path": str(scope.log_path("idle")), "since": None,
    }  # fmt: skip


def test_status_filters_by_pattern_and_survives_a_stale_socket(tmp_path: Path) -> None:
    scope = Scope.of(tmp_path, "e1")
    socket = SocketLayout(1, Path("/run")).socket_path(scope)
    socket.parent.mkdir(parents=True)
    socket.touch()
    doc = _status(FakeClient()).document(
        scope, (Service(name="a", cmd="x"), Service(name="b", cmd="x")), [ScopePattern.parse("e1/b")], {}
    )
    assert [s["name"] for s in doc["envs"][0]["services"]] == ["b"]
    assert doc["envs"][0]["services"][0]["state"] == "stopped"


def test_status_requires_the_binary(tmp_path: Path) -> None:
    with pytest.raises(ProcessComposeError, match="not on PATH"):
        _status(FakeClient(available=False)).document(Scope.of(tmp_path, "e1"), (), [], {})

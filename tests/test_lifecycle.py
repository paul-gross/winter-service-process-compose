from __future__ import annotations

from pathlib import Path

import pytest

from process_compose_orchestrator.core.errors import ProcessComposeError
from process_compose_orchestrator.core.patterns import ScopePattern
from process_compose_orchestrator.core.scope import Scope
from process_compose_orchestrator.modules.instance.config_renderer import ConfigRenderer
from process_compose_orchestrator.modules.instance.instance_state import IInstanceStateStore, InstanceState
from process_compose_orchestrator.modules.instance.internal.file_instance_state_store import FileInstanceStateStore
from process_compose_orchestrator.modules.instance.lifecycle_service import InstanceKind, InstanceLifecycleService
from process_compose_orchestrator.modules.instance.socket_layout import SocketLayout
from process_compose_orchestrator.modules.manifest.model import Health, HealthType, Service
from tests.fakes import FakeClient, FakeClock, FakeNotifier, FakeReaper, FakeStateStore, proc

SERVICES = (
    Service(name="db", cmd="run db", health=Health(HealthType.CMD, "true")),
    Service(name="api", cmd="run api", health=Health(HealthType.URL, "http://localhost:80/h"), depends_on=("db",)),
    Service(name="worker", cmd="run worker"),
)
ALL = ScopePattern.parse("e1")


class Rig:
    def __init__(self, tmp_path: Path, *, available: bool = True, store: IInstanceStateStore | None = None) -> None:
        self.scope = Scope.of(tmp_path, "e1")
        self.client = FakeClient(available=available)
        self.reaper = FakeReaper()
        self.store = FakeStateStore()
        self.clock = FakeClock()
        self.notes = FakeNotifier()
        self.layout = SocketLayout(1000, tmp_path / "r")
        self.svc = InstanceLifecycleService(
            self.client, self.reaper, store or self.store, self.layout, ConfigRenderer(), self.clock, self.notes,
        )  # fmt: skip
        self.socket = self.layout.socket_path(self.scope)

    def up(self, pattern: ScopePattern = ALL, services: tuple[Service, ...] = SERVICES, timeout: float = 10.0) -> None:
        self.svc.up(self.scope, services, pattern, {}, timeout)


def test_fresh_up_launches_disabled_then_enables_through_update(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.up()
    assert all(p.get("disabled") for p in rig.client.launched_configs[0]["processes"].values())
    assert not any(p.get("disabled") for p in rig.client.updated_configs[-1]["processes"].values())
    assert rig.store.states["e1"] == InstanceState(sid=4242, socket=str(rig.socket))


def test_up_on_live_instance_only_updates(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.up()
    rig.client.calls.clear()
    rig.up()
    assert [c[0] for c in rig.client.calls] == ["update"]


def test_up_recovers_a_stale_socket_before_a_fresh_start(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.socket.parent.mkdir(parents=True)
    rig.socket.touch()
    rig.store.states["e1"] = InstanceState(sid=77, socket=str(rig.socket))
    rig.up()
    assert rig.reaper.reaped == [77]
    assert [c[0] for c in rig.client.calls][:2] == ["launch", "update"]


def test_stale_recovery_refuses_when_daemon_pid_is_alive(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.socket.parent.mkdir(parents=True)
    rig.socket.touch()
    rig.store.states["e1"] = InstanceState(sid=77, socket=str(rig.socket))
    rig.reaper.alive_pids = {77}
    with pytest.raises(ProcessComposeError, match="alive but not answering"):
        rig.up()
    assert rig.reaper.reaped == []


def test_partial_up_starts_matched_service_and_its_dependencies_only(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.up(ScopePattern.parse("e1/api"))
    enabled = {n for n, p in rig.client.updated_configs[-1]["processes"].items() if not p.get("disabled")}
    assert enabled == {"api", "db"}


def test_fresh_up_enables_each_dependency_before_its_dependents(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.up()
    waves = [{n for n, p in c["processes"].items() if not p.get("disabled")} for c in rig.client.updated_configs]
    assert waves == [{"db", "worker"}, {"db", "worker", "api"}]


def test_up_refuses_a_depends_on_cycle(tmp_path: Path) -> None:
    cyclic = (Service(name="a", cmd="x", depends_on=("b",)), Service(name="b", cmd="x", depends_on=("a",)))
    with pytest.raises(ProcessComposeError, match="cycle"):
        Rig(tmp_path).up(services=cyclic)


def test_partial_up_on_live_keeps_running_services_enabled(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.up(ScopePattern.parse("e1/db"))
    rig.up(ScopePattern.parse("e1/worker"))
    enabled = {n for n, p in rig.client.updated_configs[1]["processes"].items() if not p.get("disabled")}
    assert enabled == {"db", "worker"}


def test_up_starts_a_stopped_selected_service_after_update(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.up()
    rig.client.after_update = [proc("db", "Completed"), proc("api", ready="Ready", probe=True), proc("worker")]
    rig.up()
    assert ("start", "db") in rig.client.calls


def test_up_with_no_services_is_a_noop_with_a_note(tmp_path: Path) -> None:
    rig = Rig(tmp_path, available=False)
    rig.up(services=())
    assert rig.client.calls == []
    assert "no services" in rig.notes.notes[0]


def test_up_unmatched_pattern_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ProcessComposeError, match="matches"):
        Rig(tmp_path).up(ScopePattern.parse("e1/nope"))


def test_up_readiness_timeout_names_unready_services(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.client.after_update = [proc("db", ready="Ready", probe=True), proc("api", ready="Not Ready", probe=True)]
    with pytest.raises(ProcessComposeError, match="not ready after 10s: api"):
        rig.up()


def test_up_fails_fast_when_a_probed_service_dies(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.client.after_update = [proc("db", ready="Ready", probe=True), proc("api", "Error", ready="-", probe=True)]
    with pytest.raises(ProcessComposeError, match="failed before becoming ready"):
        rig.up()
    assert rig.clock.now == 0


def test_up_waits_until_ready(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.client.after_update = [proc("db", ready="Ready", probe=True), proc("api", ready="Not Ready", probe=True)]
    rig.client.on_poll = [
        [proc("db", ready="Ready", probe=True), proc("api", ready="Not Ready", probe=True)],
        [proc("db", ready="Ready", probe=True), proc("api", ready="Ready", probe=True)],
    ]
    rig.up()
    assert rig.clock.now > 0


def test_missing_binary_is_reported_with_install_guidance(tmp_path: Path) -> None:
    with pytest.raises(ProcessComposeError, match="process-compose binary is not on PATH"):
        Rig(tmp_path, available=False).up()


def test_down_whole_scope_uses_client_down_and_clears_state(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.up()
    rig.svc.down(rig.scope, ALL)
    assert ("down", str(rig.socket)) in rig.client.calls
    assert "e1" not in rig.store.states


def test_down_partial_stops_only_matched_and_leaves_daemon(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.up()
    rig.svc.down(rig.scope, ScopePattern.parse("e1/wor*"))
    assert ("stop", "worker") in rig.client.calls
    assert not any(c[0] == "down" for c in rig.client.calls)
    assert rig.socket in rig.client.alive


def test_down_with_no_instance_is_exit_zero_noop(tmp_path: Path) -> None:
    rig = Rig(tmp_path, available=False)
    rig.svc.down(rig.scope, ALL)
    assert rig.client.calls == []


def test_down_stale_reaps_without_the_binary(tmp_path: Path) -> None:
    rig = Rig(tmp_path, available=False)
    rig.socket.parent.mkdir(parents=True)
    rig.socket.touch()
    rig.store.states["e1"] = InstanceState(sid=9, socket=str(rig.socket))
    rig.svc.down(rig.scope, ALL)
    assert rig.reaper.reaped == [9]
    assert not rig.socket.exists()
    assert "e1" not in rig.store.states


def test_restart_restarts_matches_and_requires_a_live_instance(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    with pytest.raises(ProcessComposeError, match="no running instance"):
        rig.svc.restart(rig.scope, ["worker"])
    rig.up()
    rig.svc.restart(rig.scope, ["wor*"])
    assert ("restart", "worker") in rig.client.calls
    with pytest.raises(ProcessComposeError, match="matches"):
        rig.svc.restart(rig.scope, ["zzz"])


def _ghost_rig(tmp_path: Path, *, available: bool = True) -> tuple[Rig, Scope]:
    """A rig plus a scope whose env directory does not exist."""
    rig = Rig(tmp_path, available=available)
    ghost = Scope.of(tmp_path, "ghost")
    rig.store.missing_roots.add(ghost.name)
    return rig, ghost


def _tree(path: Path) -> list[str]:
    return sorted(str(p.relative_to(path)) for p in path.rglob("*"))


def test_down_of_a_missing_env_notes_and_creates_nothing(tmp_path: Path) -> None:
    rig, ghost = _ghost_rig(tmp_path, available=False)
    before = _tree(tmp_path)
    rig.svc.down(ghost, ScopePattern.parse("ghost"))
    assert rig.notes.notes == ["scope 'ghost' has no running instance"]
    assert rig.client.calls == []
    assert rig.store.locked == []
    assert _tree(tmp_path) == before


def test_restart_of_a_missing_env_errors_like_a_stopped_scope_and_creates_nothing(tmp_path: Path) -> None:
    rig, ghost = _ghost_rig(tmp_path)
    before = _tree(tmp_path)
    with pytest.raises(ProcessComposeError, match="no running instance to restart"):
        rig.svc.restart(ghost, ["api"])
    assert _tree(tmp_path) == before


def test_up_of_a_missing_env_names_the_directory_and_creates_nothing(tmp_path: Path) -> None:
    rig, ghost = _ghost_rig(tmp_path)
    before = _tree(tmp_path)
    with pytest.raises(ProcessComposeError, match=r"env directory .*ghost does not exist"):
        rig.svc.up(ghost, SERVICES, ScopePattern.parse("ghost"), {}, 10.0)
    assert rig.client.calls == []
    assert _tree(tmp_path) == before


def test_status_of_a_missing_env_reports_nothing_running_and_creates_nothing(tmp_path: Path) -> None:
    rig, ghost = _ghost_rig(tmp_path)
    before = _tree(tmp_path)
    assert rig.svc.inspect(ghost).kind is InstanceKind.ABSENT
    assert _tree(tmp_path) == before


def _orphaned_rig(tmp_path: Path, store: IInstanceStateStore | None = None) -> tuple[Rig, Scope, Path]:
    """A rig whose scope root is gone while a daemon still answers on its fallback socket (long root path)."""
    rig = Rig(tmp_path, store=store)
    orphan = Scope.of(tmp_path, "g" * 120)
    rig.store.missing_roots.add(orphan.name)
    socket = rig.layout.socket_path(orphan)
    assert not socket.is_relative_to(orphan.root)
    socket.parent.mkdir(parents=True)
    socket.touch()
    rig.client.alive[socket] = [proc("api"), proc("worker")]
    return rig, orphan, socket


def test_down_stops_a_live_fallback_socket_daemon_whose_root_is_gone(tmp_path: Path) -> None:
    rig, orphan, socket = _orphaned_rig(tmp_path)
    assert rig.svc.inspect(orphan).kind is InstanceKind.LIVE
    rig.svc.down(orphan, ScopePattern.parse(orphan.name))
    assert ("down", str(socket)) in rig.client.calls
    assert not socket.exists()
    assert rig.store.locked == []
    assert not orphan.root.exists()
    assert rig.svc.inspect(orphan).kind is InstanceKind.ABSENT


def test_down_stops_that_daemon_through_the_real_store_without_creating_the_root(tmp_path: Path) -> None:
    rig, orphan, socket = _orphaned_rig(tmp_path, FileInstanceStateStore())
    rig.svc.down(orphan, ScopePattern.parse(orphan.name))
    assert ("down", str(socket)) in rig.client.calls
    assert not socket.exists()
    assert not orphan.root.exists()


def test_partial_down_stops_matching_processes_of_that_daemon(tmp_path: Path) -> None:
    rig, orphan, socket = _orphaned_rig(tmp_path)
    rig.svc.down(orphan, ScopePattern.parse(f"{orphan.name}/api"))
    assert rig.client.calls == [("stop", "api")]
    assert socket.exists()


def test_down_clears_a_dead_fallback_socket_whose_root_is_gone(tmp_path: Path) -> None:
    rig, orphan, socket = _orphaned_rig(tmp_path)
    del rig.client.alive[socket]
    rig.svc.down(orphan, ScopePattern.parse(orphan.name))
    assert not socket.exists()
    assert rig.client.calls == []
    assert not orphan.root.exists()


def test_restart_restarts_a_live_fallback_socket_daemon_whose_root_is_gone(tmp_path: Path) -> None:
    rig, orphan, _ = _orphaned_rig(tmp_path)
    rig.svc.restart(orphan, ["api"])
    assert rig.client.calls == [("restart", "api")]
    assert rig.store.locked == []
    assert not orphan.root.exists()


def test_up_of_a_scope_whose_root_is_gone_still_names_the_directory(tmp_path: Path) -> None:
    rig, orphan, _ = _orphaned_rig(tmp_path)
    with pytest.raises(ProcessComposeError, match=r"env directory .* does not exist"):
        rig.svc.up(orphan, SERVICES, ScopePattern.parse(orphan.name), {}, 10.0)
    assert rig.client.calls == []


def test_the_store_lock_refuses_a_missing_scope_root_without_creating_it(tmp_path: Path) -> None:
    ghost = Scope.of(tmp_path, "ghost")
    lock = FileInstanceStateStore().lock(ghost)
    with pytest.raises(ProcessComposeError, match=r"env directory .*ghost does not exist"), lock:
        pass
    assert not ghost.root.exists()


def test_the_store_lock_creates_the_state_directory_on_demand_for_an_existing_root(tmp_path: Path) -> None:
    scope = Scope.of(tmp_path, "e1")
    scope.root.mkdir()
    with FileInstanceStateStore().lock(scope):
        assert scope.lock_path.exists()


def test_the_store_reports_whether_a_scope_root_exists(tmp_path: Path) -> None:
    store = FileInstanceStateStore()
    (tmp_path / "e1").mkdir()
    assert store.scope_root_exists(Scope.of(tmp_path, "e1"))
    assert not store.scope_root_exists(Scope.of(tmp_path, "ghost"))
    assert store.scope_root_exists(Scope.of(tmp_path, "workspace"))

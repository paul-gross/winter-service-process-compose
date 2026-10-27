from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from process_compose_orchestrator.cli import _parse_log_args, main
from process_compose_orchestrator.core.errors import ProcessComposeError
from process_compose_orchestrator.core.patterns import ScopePattern
from process_compose_orchestrator.core.scope import Scope
from process_compose_orchestrator.modules.logs.internal.file_log_source import FileLogSource
from process_compose_orchestrator.modules.logs.log_entry import parse_line
from process_compose_orchestrator.modules.logs.log_service import LogOptions, LogService
from tests.fakes import FakeFollowClock, FakeLogSource

SCOPE = Scope.of(Path("/ws"), "alpha")


def line(message: str, time: str = "2026-10-22T06:00:01.123456789-05:00", level: str = "info") -> str:
    return json.dumps({"level": level, "process": "x", "replica": 0, "time": time, "message": message}) + "\n"


def run(files: dict[str, str], patterns: list[str], options: LogOptions, clock: FakeFollowClock | None = None):
    source = FakeLogSource({SCOPE.log_path(n): t for n, t in files.items()})
    out: list[str] = []
    LogService(source, clock or FakeFollowClock(0), out.append).run(
        SCOPE, tuple(files), [ScopePattern.parse(p) for p in patterns], options
    )
    return source, [json.loads(o) for o in out]


# --- entry parsing ----------------------------------------------------------------------------------------------


def test_timestamp_normalized_to_microsecond_utc() -> None:
    entry = parse_line(line("hello"))
    assert entry is not None
    assert entry.ts == "2026-10-22T11:00:01.123456Z"
    assert entry.msg == "hello"


def test_trailing_newline_stripped_once_and_bare_newline_dropped() -> None:
    assert parse_line(line("text\n")).msg == "text"  # type: ignore[union-attr]
    assert parse_line(line("a\n\n")).msg == "a\n"  # type: ignore[union-attr]
    assert parse_line(line("\n")) is None
    assert parse_line(line("")) is None


def test_non_json_line_kept_without_timestamp() -> None:
    entry = parse_line("plain output")
    assert entry is not None
    assert entry.ts is None
    assert entry.to_wire("alpha", "api") == {"env": "alpha", "svc": "api", "msg": "plain output"}


# --- service: tail, window, merge -------------------------------------------------------------------------------


def test_tail_limits_each_service() -> None:
    text = "".join(line(f"m{i}", f"2026-10-22T06:00:0{i}Z") for i in range(5))
    _, out = run({"api": text, "web": text}, ["alpha"], LogOptions(tail=2))
    assert [o["msg"] for o in out if o["svc"] == "api"] == ["m3", "m4"]
    assert [o["msg"] for o in out if o["svc"] == "web"] == ["m3", "m4"]


def test_tail_all_and_zero() -> None:
    text = "".join(line(f"m{i}") for i in range(3))
    assert len(run({"api": text}, ["alpha"], LogOptions(tail=None))[1]) == 3
    assert run({"api": text}, ["alpha"], LogOptions(tail=0))[1] == []


def test_since_until_inclusive() -> None:
    text = "".join(line(f"m{i}", f"2026-10-22T06:00:0{i}Z") for i in range(5))
    opts = LogOptions(
        since=datetime(2026, 10, 22, 6, 0, 1, tzinfo=UTC), until=datetime(2026, 10, 22, 6, 0, 3, tzinfo=UTC)
    )
    assert [o["msg"] for o in run({"api": text}, ["alpha"], opts)[1]] == ["m1", "m2", "m3"]


def test_services_merged_by_time_and_pattern_filters() -> None:
    api = line("a1", "2026-10-22T06:00:01Z") + line("a3", "2026-10-22T06:00:03Z")
    web = line("w2", "2026-10-22T06:00:02Z")
    _, out = run({"api": api, "web": web}, ["alpha"], LogOptions())
    assert [o["msg"] for o in out] == ["a1", "w2", "a3"]
    _, only = run({"api": api, "web": web}, ["alpha/web"], LogOptions())
    assert [o["svc"] for o in only] == ["web"]


def test_undeclared_service_with_a_log_file_is_read() -> None:
    source = FakeLogSource({SCOPE.log_path("extra"): line("hi")})
    out: list[str] = []
    LogService(source, FakeFollowClock(0), out.append).run(SCOPE, (), [ScopePattern.parse("alpha")], LogOptions())
    assert json.loads(out[0])["svc"] == "extra"


# --- follow -----------------------------------------------------------------------------------------------------


def test_follow_streams_appended_lines() -> None:
    path = SCOPE.log_path("api")
    source = FakeLogSource({path: line("one")})
    out: list[str] = []

    def append(n: int) -> None:
        source.files[path] += line(f"later{n}")

    LogService(source, FakeFollowClock(2, append), out.append).run(
        SCOPE, ("api",), [ScopePattern.parse("alpha")], LogOptions(follow=True, tail=1)
    )
    assert [json.loads(o)["msg"] for o in out] == ["one", "later1", "later2"]


def test_follow_reopens_from_start_after_truncation() -> None:
    path = SCOPE.log_path("api")
    source = FakeLogSource({path: line("old-one") + line("old-two")})
    out: list[str] = []

    def truncate(n: int) -> None:
        source.files[path] = line("new")

    LogService(source, FakeFollowClock(1, truncate), out.append).run(
        SCOPE, ("api",), [ScopePattern.parse("alpha")], LogOptions(follow=True)
    )
    assert [json.loads(o)["msg"] for o in out] == ["old-one", "old-two", "new"]


def test_follow_picks_up_a_log_file_created_later() -> None:
    source = FakeLogSource()
    out: list[str] = []

    def create(n: int) -> None:
        source.files[SCOPE.log_path("api")] = line("born")

    LogService(source, FakeFollowClock(2, create), out.append).run(
        SCOPE, ("api",), [ScopePattern.parse("alpha")], LogOptions(follow=True)
    )
    assert [json.loads(o)["msg"] for o in out] == ["born"]


# --- file adapter -----------------------------------------------------------------------------------------------


def test_file_source_holds_back_partial_line_and_detects_truncation(tmp_path: Path) -> None:
    source = FileLogSource()
    log = tmp_path / "api.log"
    assert source.poll(log, 5) == ([], 0)
    log.write_text("a\nb")
    lines, offset = source.poll(log, 0)
    assert (lines, offset) == (["a"], 2)
    log.write_text("a\nb\nc\n")
    assert source.poll(log, offset) == (["b", "c"], 6)
    log.write_text("z\n")
    assert source.poll(log, 6) == (["z"], 2)
    assert source.services(tmp_path) == ["api"]
    assert source.services(tmp_path / "missing") == []


# --- flag mapping -----------------------------------------------------------------------------------------------


def test_flag_mapping() -> None:
    patterns, opts = _parse_log_args(
        ["a/api", "b", "-f", "-n", "7", "--since", "2026-10-22T06:00:00Z", "--until", "2026-10-22T07:00:00.5Z", "-t"]
    )
    assert [(p.scope, p.service) for p in patterns] == [("a", "api"), ("b", "*")]
    assert opts.follow
    assert opts.tail == 7
    assert opts.since == datetime(2026, 10, 22, 6, tzinfo=UTC)
    assert opts.until == datetime(2026, 10, 22, 7, 0, 0, 500000, tzinfo=UTC)
    assert _parse_log_args(["a", "--tail", "all"])[1].tail is None


@pytest.mark.parametrize("args", [["a", "-n"], ["a", "-n", "x"], ["a", "--since", "yesterday"], ["a", "--bogus"]])
def test_bad_flags_refused(args: list[str]) -> None:
    with pytest.raises(ProcessComposeError):
        _parse_log_args(args)


def test_logs_without_binary_names_the_binary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.setenv("WINTER_WORKSPACE_DIR", "/ws")
    assert main(["logs", "alpha/api", "-n", "5"]) == 1
    assert "process-compose" in capsys.readouterr().err


def test_logs_of_a_missing_env_emit_nothing_and_create_nothing(tmp_path: Path) -> None:
    out: list[str] = []
    ghost = Scope.of(tmp_path, "ghost")
    LogService(FileLogSource(), FakeFollowClock(), out.append).run(
        ghost, ("api",), [ScopePattern.parse("ghost/api")], LogOptions()
    )
    assert out == []
    assert list(tmp_path.iterdir()) == []

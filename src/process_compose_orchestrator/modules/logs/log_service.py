"""Reads per-service log files and emits winter's ``logs`` NDJSON, optionally following them."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from process_compose_orchestrator.core.patterns import ScopePattern, matches
from process_compose_orchestrator.core.scope import Scope
from process_compose_orchestrator.modules.logs.log_entry import LogEntry, parse_line
from process_compose_orchestrator.modules.logs.log_source import IFollowClock, ILogSource

_POLL_SECONDS = 0.25


@dataclass(frozen=True)
class LogOptions:
    follow: bool = False
    tail: int | None = None  # ``None`` is ``all``
    since: datetime | None = None
    until: datetime | None = None


class LogService:
    def __init__(self, source: ILogSource, clock: IFollowClock, write: Callable[[str], None]) -> None:
        self._source = source
        self._clock = clock
        self._write = write

    def run(self, scope: Scope, declared: tuple[str, ...], patterns: list[ScopePattern], options: LogOptions) -> None:
        """Emit the backlog of every matched service (merged by time), then follow when asked."""
        names = sorted({*declared, *self._source.services(scope.log_dir)})
        matched = [n for n in names if matches(patterns, scope.name, n)]
        offsets: dict[str, int] = {}
        backlog: list[tuple[LogEntry, str]] = []
        for name in matched:
            lines, offsets[name] = self._source.poll(scope.log_path(name), 0)
            entries = [e for e in map(parse_line, lines) if e is not None and self._in_window(e, options)]
            if options.tail is not None:
                entries = entries[-options.tail :] if options.tail > 0 else []
            backlog.extend((e, name) for e in entries)
        backlog.sort(key=lambda pair: pair[0].moment or datetime.min.replace(tzinfo=UTC))
        for entry, name in backlog:
            self._emit(scope, name, entry)
        if not options.follow:
            return
        while self._clock.keep_following():
            progressed = False
            for name in self._followed(scope, declared, patterns):
                lines, offsets[name] = self._source.poll(scope.log_path(name), offsets.get(name, 0))
                for entry in filter(None, map(parse_line, lines)):
                    if self._in_window(entry, options):
                        self._emit(scope, name, entry)
                        progressed = True
            if not progressed:
                self._clock.sleep(_POLL_SECONDS)

    def _followed(self, scope: Scope, declared: tuple[str, ...], patterns: list[ScopePattern]) -> list[str]:
        """Matched services, including any that gained a log file since the loop began."""
        current = sorted({*declared, *self._source.services(scope.log_dir)})
        return [n for n in current if matches(patterns, scope.name, n)]

    @staticmethod
    def _in_window(entry: LogEntry, options: LogOptions) -> bool:
        if entry.moment is None:
            return True
        if options.since is not None and entry.moment < options.since:
            return False
        return not (options.until is not None and entry.moment > options.until)

    def _emit(self, scope: Scope, name: str, entry: LogEntry) -> None:
        self._write(json.dumps(entry.to_wire(scope.name, name)) + "\n")

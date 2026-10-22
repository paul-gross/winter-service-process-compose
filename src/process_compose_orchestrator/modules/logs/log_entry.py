"""Pure translation of one process-compose log line into a winter NDJSON entry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from process_compose_orchestrator.core.timestamps import normalize_timestamp, parse_rfc3339


@dataclass(frozen=True)
class LogEntry:
    ts: str | None
    moment: datetime | None
    msg: str

    def to_wire(self, env: str, svc: str) -> dict[str, str]:
        wire = {"env": env, "svc": svc, "msg": self.msg}
        if self.ts is not None:
            wire["ts"] = self.ts
        return wire


def parse_line(raw: str) -> LogEntry | None:
    """One JSON log line -> entry; ``None`` for the bare-newline artifacts process-compose writes.

    A line that is not a JSON object is kept verbatim, without a timestamp.
    """
    try:
        record = json.loads(raw)
    except ValueError:
        record = None
    if not isinstance(record, dict):
        return LogEntry(None, None, raw) if raw.strip() else None
    message = record.get("message")
    text = message if isinstance(message, str) else ""
    text = text.removesuffix("\n").removesuffix("\r")
    if not text.strip():
        return None
    time_raw = record.get("time")
    time_str = time_raw if isinstance(time_raw, str) else None
    return LogEntry(normalize_timestamp(time_str), parse_rfc3339(time_str), text)

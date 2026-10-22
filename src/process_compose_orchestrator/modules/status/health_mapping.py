"""Pure mapping from process-compose process facts onto the service-v1 status vocabulary."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from process_compose_orchestrator.modules.instance.lifecycle_service import TERMINAL_STATUSES
from process_compose_orchestrator.modules.instance.process_compose_client import ProcessInfo

_FRACTION_RE = re.compile(r"\.(\d+)")


def map_state(process: ProcessInfo) -> str:
    if process.status == "Running":
        return "running"
    if process.status in TERMINAL_STATUSES:
        return "stopped"
    return "unknown"


def map_health(process: ProcessInfo) -> str:
    """``healthy`` only when ready; a probed process that is not ready (in any state) is ``unhealthy``."""
    if process.is_ready == "Ready":
        return "healthy"
    if process.has_ready_probe:
        return "unhealthy"
    return "unknown"


def normalize_since(raw: str | None) -> str | None:
    """RFC3339 with nanoseconds and an offset -> microsecond UTC ``...Z``; ``None`` when unparseable."""
    if not raw:
        return None
    try:
        trimmed = _FRACTION_RE.sub(lambda m: "." + m.group(1)[:6].ljust(6, "0"), raw, count=1)
        parsed = datetime.fromisoformat(trimmed)
    except ValueError:
        return None
    if parsed.year < 2000:
        return None
    return parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

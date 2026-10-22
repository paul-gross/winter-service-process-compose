"""Pure mapping from process-compose process facts onto the service-v1 status vocabulary."""

from __future__ import annotations

from process_compose_orchestrator.core.timestamps import normalize_timestamp
from process_compose_orchestrator.modules.instance.lifecycle_service import TERMINAL_STATUSES
from process_compose_orchestrator.modules.instance.process_compose_client import ProcessInfo


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


normalize_since = normalize_timestamp

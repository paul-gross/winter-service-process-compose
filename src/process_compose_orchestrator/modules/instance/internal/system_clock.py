"""Wall-clock ``IClock``."""

from __future__ import annotations

import time

from process_compose_orchestrator.modules.instance.clock import IClock


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def _conforms_clock(adapter: SystemClock) -> IClock:
    return adapter

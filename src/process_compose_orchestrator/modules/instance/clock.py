"""Time seam, so readiness polling and daemon-start waits are testable without real sleeps."""

from __future__ import annotations

from typing import Protocol


class IClock(Protocol):
    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...

"""Diagnostics seam: human notes go to stderr, never to the wire-contract stdout."""

from __future__ import annotations

from typing import Protocol


class INotifier(Protocol):
    def note(self, message: str) -> None: ...

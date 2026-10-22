"""Stderr ``INotifier``."""

from __future__ import annotations

import sys

from process_compose_orchestrator.modules.instance.notifier import INotifier


class StderrNotifier:
    def note(self, message: str) -> None:
        print(f"process-compose-orchestrator: {message}", file=sys.stderr)


def _conforms_stderr_notifier(x: StderrNotifier) -> INotifier:
    return x

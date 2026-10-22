"""Composition root — the single place Protocols are bound to concrete adapters."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from process_compose_orchestrator.core.errors import ProcessComposeErrorFactory
from process_compose_orchestrator.modules.instance.config_renderer import ConfigRenderer
from process_compose_orchestrator.modules.instance.internal.cli_process_compose_client import CliProcessComposeClient
from process_compose_orchestrator.modules.instance.internal.file_instance_state_store import FileInstanceStateStore
from process_compose_orchestrator.modules.instance.internal.proc_session_reaper import ProcSessionReaper
from process_compose_orchestrator.modules.instance.internal.stderr_notifier import StderrNotifier
from process_compose_orchestrator.modules.instance.internal.system_clock import SystemClock
from process_compose_orchestrator.modules.instance.lifecycle_service import InstanceLifecycleService
from process_compose_orchestrator.modules.instance.socket_layout import SocketLayout
from process_compose_orchestrator.modules.logs.internal.file_log_source import FileLogSource, WallFollowClock
from process_compose_orchestrator.modules.logs.log_service import LogService
from process_compose_orchestrator.modules.manifest.catalog_service import CatalogService
from process_compose_orchestrator.modules.manifest.internal.toml_ext_manifest_reader import TomlExtManifestReader
from process_compose_orchestrator.modules.manifest.internal.toml_manifest_reader import TomlManifestReader
from process_compose_orchestrator.modules.manifest.manifest_loader import ManifestLoader
from process_compose_orchestrator.modules.manifest.validator import ManifestValidator
from process_compose_orchestrator.modules.status.status_service import StatusService


class Container:
    """Builds the provider's services with production adapters."""

    def __init__(self) -> None:
        self._manifest_reader = TomlManifestReader()
        self._ext_manifest_reader = TomlExtManifestReader()
        self._validator = ManifestValidator()
        self._errors = ProcessComposeErrorFactory()
        self._clock = SystemClock()
        self._notifier = StderrNotifier()

    def catalog_service(self) -> CatalogService:
        return CatalogService(self._manifest_reader, self._validator)

    def manifest_loader(self) -> ManifestLoader:
        return ManifestLoader(self._manifest_reader, self._ext_manifest_reader, self._validator)

    def notifier(self) -> StderrNotifier:
        return self._notifier

    def instance_lifecycle(self) -> InstanceLifecycleService:
        runtime_dir = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir())
        return InstanceLifecycleService(
            client=CliProcessComposeClient(self._errors, self._clock),
            reaper=ProcSessionReaper(self._clock),
            store=FileInstanceStateStore(),
            layout=SocketLayout(os.getuid(), runtime_dir),
            renderer=ConfigRenderer(),
            clock=self._clock,
            notifier=self._notifier,
        )

    def status_service(self) -> StatusService:
        return StatusService(self.instance_lifecycle(), self._notifier)

    def log_service(self, write: Callable[[str], None]) -> LogService:
        return LogService(FileLogSource(), WallFollowClock(), write)

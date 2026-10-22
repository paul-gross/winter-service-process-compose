"""Protocol seams for reading manifests."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from process_compose_orchestrator.modules.manifest.model import ExtServices, ServiceManifest


class IManifestReader(Protocol):
    """Reads the workspace's ``config.toml`` into a ``ServiceManifest``; raises ``ManifestError``."""

    def read(self, config_dir: Path) -> ServiceManifest: ...


class IExtManifestReader(Protocol):
    """Reads the aggregated ``WINTER_SERVICE_MANIFEST`` file into runnable extension services."""

    def read(self, path: Path) -> ExtServices: ...

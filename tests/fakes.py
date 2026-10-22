"""In-memory fakes for every Protocol seam."""

from __future__ import annotations

from pathlib import Path

from process_compose_orchestrator.modules.manifest.errors import ManifestError
from process_compose_orchestrator.modules.manifest.model import ExtServices, ServiceManifest


class FakeManifestReader:
    """Returns a canned manifest, or raises when constructed with an error."""

    def __init__(self, manifest: ServiceManifest | None = None, error: ManifestError | None = None) -> None:
        self._manifest = manifest or ServiceManifest()
        self._error = error
        self.read_dirs: list[Path] = []

    def read(self, config_dir: Path) -> ServiceManifest:
        self.read_dirs.append(config_dir)
        if self._error is not None:
            raise self._error
        return self._manifest


class FakeExtManifestReader:
    """Returns canned extension services."""

    def __init__(self, ext: ExtServices | None = None) -> None:
        self._ext = ext or ExtServices()
        self.read_paths: list[Path] = []

    def read(self, path: Path) -> ExtServices:
        self.read_paths.append(path)
        return self._ext

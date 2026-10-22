"""``describe`` and ``catalog``: the scope-qualified names this provider owns."""

from __future__ import annotations

from pathlib import Path

from process_compose_orchestrator.modules.manifest.errors import ManifestError
from process_compose_orchestrator.modules.manifest.manifest_reader import IManifestReader
from process_compose_orchestrator.modules.manifest.model import ServiceManifest
from process_compose_orchestrator.modules.manifest.validator import ManifestValidator


class CatalogService:
    """Lists ``workspace/<name>`` for workspace-scoped and ``*/<name>`` for per-env services."""

    def __init__(self, reader: IManifestReader, validator: ManifestValidator) -> None:
        self._reader = reader
        self._validator = validator

    def describe(self, config_dir: Path) -> list[str]:
        """Names for ``describe``; raises ``ManifestError`` when the manifest is unreadable or invalid."""
        manifest = self._reader.read(config_dir)
        violations = self._validator.validate(manifest)
        if violations:
            raise ManifestError("invalid manifest:\n  " + "\n  ".join(violations))
        return self._names(manifest)

    def catalog(self, config_dir: Path) -> list[str]:
        """Names for ``catalog``; an absent or refused manifest is an empty catalog, not an error."""
        try:
            return self._names(self._reader.read(config_dir))
        except ManifestError:
            return []

    @staticmethod
    def _names(manifest: ServiceManifest) -> list[str]:
        return [
            *(f"workspace/{svc.name}" for svc in manifest.workspace_services),
            *(f"*/{svc.name}" for svc in manifest.services),
        ]

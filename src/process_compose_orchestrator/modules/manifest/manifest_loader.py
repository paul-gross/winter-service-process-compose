"""Loads the effective manifest: workspace config, validated, with extension-declared services merged in."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from process_compose_orchestrator.modules.manifest.errors import ManifestError
from process_compose_orchestrator.modules.manifest.manifest_reader import IExtManifestReader, IManifestReader
from process_compose_orchestrator.modules.manifest.model import ExtServices, Service, ServiceManifest
from process_compose_orchestrator.modules.manifest.validator import ManifestValidator


@dataclass(frozen=True)
class LoadedManifest:
    """The effective manifest plus stderr-worthy notes about skipped extension entries."""

    manifest: ServiceManifest
    notes: tuple[str, ...] = ()


class ManifestLoader:
    """Reads, validates, and merges; raises ``ManifestError`` for a refused or invalid manifest."""

    def __init__(self, reader: IManifestReader, ext_reader: IExtManifestReader, validator: ManifestValidator) -> None:
        self._reader = reader
        self._ext_reader = ext_reader
        self._validator = validator

    def load(self, config_dir: Path, ext_manifest: Path | None = None) -> LoadedManifest:
        """Load ``config_dir``'s manifest; when *ext_manifest* is given, merge its runnable services in."""
        base = self._reader.read(config_dir)
        violations = self._validator.validate(base)
        if violations:
            raise ManifestError("invalid manifest:\n  " + "\n  ".join(violations))
        if ext_manifest is None:
            return LoadedManifest(base)
        return self._merge(base, self._ext_reader.read(ext_manifest))

    @staticmethod
    def _merge(base: ServiceManifest, ext: ExtServices) -> LoadedManifest:
        declared = {svc.name for svc in (*base.services, *base.workspace_services)}
        for svc in (*ext.project, *ext.workspace):
            if svc.name in declared:
                raise ManifestError(
                    f"extension-declared service '{svc.name}' collides with a service in the workspace manifest"
                )
            declared.add(svc.name)
        project: tuple[Service, ...] = base.services + ext.project
        workspace: tuple[Service, ...] = base.workspace_services + ext.workspace
        return LoadedManifest(ServiceManifest(services=project, workspace_services=workspace), ext.notes)

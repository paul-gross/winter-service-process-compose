"""Composition root — the single place Protocols are bound to concrete adapters."""

from __future__ import annotations

from process_compose_orchestrator.modules.manifest.catalog_service import CatalogService
from process_compose_orchestrator.modules.manifest.internal.toml_ext_manifest_reader import TomlExtManifestReader
from process_compose_orchestrator.modules.manifest.internal.toml_manifest_reader import TomlManifestReader
from process_compose_orchestrator.modules.manifest.manifest_loader import ManifestLoader
from process_compose_orchestrator.modules.manifest.validator import ManifestValidator


class Container:
    """Builds the provider's services with production adapters."""

    def __init__(self) -> None:
        self._manifest_reader = TomlManifestReader()
        self._ext_manifest_reader = TomlExtManifestReader()
        self._validator = ManifestValidator()

    def catalog_service(self) -> CatalogService:
        return CatalogService(self._manifest_reader, self._validator)

    def manifest_loader(self) -> ManifestLoader:
        return ManifestLoader(self._manifest_reader, self._ext_manifest_reader, self._validator)

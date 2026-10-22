from __future__ import annotations

from pathlib import Path

import pytest

from process_compose_orchestrator.modules.manifest.catalog_service import CatalogService
from process_compose_orchestrator.modules.manifest.errors import ManifestError
from process_compose_orchestrator.modules.manifest.manifest_loader import ManifestLoader
from process_compose_orchestrator.modules.manifest.model import (
    ExtServices,
    Health,
    HealthType,
    Service,
    ServiceManifest,
)
from process_compose_orchestrator.modules.manifest.validator import ManifestValidator
from tests.fakes import FakeExtManifestReader, FakeManifestReader


def _svc(name: str, **kw) -> Service:
    return Service(name=name, cmd="true", **kw)


def test_validator_flags_dependency_problems() -> None:
    manifest = ServiceManifest(
        services=(
            _svc("a", depends_on=("a",)),
            _svc("b", depends_on=("missing",)),
            _svc("c", depends_on=("d",)),
            _svc("d", depends_on=("c",)),
        )
    )
    text = "\n".join(ManifestValidator().validate(manifest))
    assert "depends_on lists itself" in text
    assert "matches no project-scope service" in text
    assert "depends_on cycle" in text


def test_validator_flags_values_and_duplicates() -> None:
    manifest = ServiceManifest(
        services=(
            _svc("a", cwd="../out", port="nonsense", health=Health(HealthType.URL, "http://x", timeout=0)),
            _svc("a"),
        ),
        workspace_services=(_svc("a"),),
    )
    text = "\n".join(ManifestValidator().validate(manifest))
    assert "cwd" in text
    assert "port expression" in text
    assert "health.timeout" in text
    assert "duplicate service name 'a'" in text


def test_validator_accepts_clean_manifest() -> None:
    manifest = ServiceManifest(services=(_svc("a", port="WINTER_PORT_BASE + 1"), _svc("b", depends_on=("a",))))
    assert ManifestValidator().validate(manifest) == []


def test_catalog_names_are_scope_qualified() -> None:
    reader = FakeManifestReader(ServiceManifest(services=(_svc("api"),), workspace_services=(_svc("fx"),)))
    service = CatalogService(reader, ManifestValidator())
    assert service.describe(Path("/cfg")) == ["workspace/fx", "*/api"]
    assert service.catalog(Path("/cfg")) == ["workspace/fx", "*/api"]


def test_catalog_swallows_manifest_error_but_describe_raises() -> None:
    service = CatalogService(FakeManifestReader(error=ManifestError("bad")), ManifestValidator())
    assert service.catalog(Path("/cfg")) == []
    with pytest.raises(ManifestError):
        service.describe(Path("/cfg"))


def test_loader_merges_extension_services_and_carries_notes() -> None:
    base = ServiceManifest(services=(_svc("api"),))
    ext = ExtServices(project=(_svc("extra"),), workspace=(_svc("wext"),), notes=("skipped image-only",))
    loader = ManifestLoader(FakeManifestReader(base), FakeExtManifestReader(ext), ManifestValidator())
    loaded = loader.load(Path("/cfg"), Path("/ext.toml"))
    assert [s.name for s in loaded.manifest.services] == ["api", "extra"]
    assert [s.name for s in loaded.manifest.workspace_services] == ["wext"]
    assert loaded.notes == ("skipped image-only",)


def test_loader_refuses_name_collision() -> None:
    base = ServiceManifest(services=(_svc("api"),))
    loader = ManifestLoader(
        FakeManifestReader(base), FakeExtManifestReader(ExtServices(project=(_svc("api"),))), ManifestValidator()
    )
    with pytest.raises(ManifestError, match="collides"):
        loader.load(Path("/cfg"), Path("/ext.toml"))


def test_loader_without_extension_manifest_skips_ext_reader() -> None:
    ext_reader = FakeExtManifestReader()
    loader = ManifestLoader(FakeManifestReader(ServiceManifest()), ext_reader, ManifestValidator())
    loader.load(Path("/cfg"))
    assert ext_reader.read_paths == []


def test_loader_rejects_invalid_manifest() -> None:
    base = ServiceManifest(services=(_svc("a", depends_on=("zzz",)),))
    loader = ManifestLoader(FakeManifestReader(base), FakeExtManifestReader(), ManifestValidator())
    with pytest.raises(ManifestError, match="invalid manifest"):
        loader.load(Path("/cfg"))

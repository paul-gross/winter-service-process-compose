"""TOML adapter for ``IExtManifestReader``: reads the aggregated ``WINTER_SERVICE_MANIFEST`` file.

Extension entries carry ``name``, ``scope`` (``workspace`` or ``feature-environment``), and either ``cmd`` or
``image``. Only entries with a ``cmd`` are runnable here; the rest are skipped with a note, never an error, so one
extension's declaration cannot break ``up``.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from process_compose_orchestrator.modules.manifest.manifest_reader import IExtManifestReader
from process_compose_orchestrator.modules.manifest.model import ExtServices, Service

_SCOPES = ("workspace", "feature-environment")


class TomlExtManifestReader:
    """Reads the extension-service manifest at *path*; unreadable input yields an empty result plus a note."""

    def read(self, path: Path) -> ExtServices:
        try:
            doc = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
            return ExtServices(notes=(f"ext-manifest: cannot read {path}: {exc}",))
        raw_services = doc.get("service", [])
        if not isinstance(raw_services, list):
            return ExtServices(notes=(f"ext-manifest: [[service]] in {path} must be a list",))

        project: list[Service] = []
        workspace: list[Service] = []
        notes: list[str] = []
        for i, raw in enumerate(raw_services):
            if not isinstance(raw, dict):
                notes.append(f"ext-manifest: [[service]][{i}] is not a table, skipping")
                continue
            name = raw.get("name")
            if not isinstance(name, str) or not name:
                notes.append(f"ext-manifest: [[service]][{i}] has no 'name', skipping")
                continue
            scope = raw.get("scope", "feature-environment")
            if scope not in _SCOPES:
                notes.append(f"ext-manifest: service {name!r} has unknown scope {scope!r}, skipping")
                continue
            cmd = raw.get("cmd", raw.get("command"))
            if not isinstance(cmd, str) or not cmd.strip():
                notes.append(f"ext-manifest: service {name!r} has no 'cmd' (image-only?), skipping")
                continue
            (workspace if scope == "workspace" else project).append(Service(name=name, cmd=cmd))
        return ExtServices(project=tuple(project), workspace=tuple(workspace), notes=tuple(notes))


def _conforms_toml_ext_manifest_reader(x: TomlExtManifestReader) -> IExtManifestReader:
    return x

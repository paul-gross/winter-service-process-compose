from __future__ import annotations

import json
from pathlib import Path

import pytest

from process_compose_orchestrator import cli
from process_compose_orchestrator.modules.manifest.internal.toml_ext_manifest_reader import TomlExtManifestReader


def test_ext_reader_partitions_by_scope_and_skips_image_only(tmp_path: Path) -> None:
    path = tmp_path / "ext.toml"
    path.write_text(
        '[[service]]\nname = "a"\nscope = "feature-environment"\ncmd = "run a"\n'
        '[[service]]\nname = "w"\nscope = "workspace"\ncmd = "run w"\n'
        '[[service]]\nname = "img"\nscope = "workspace"\nimage = "x:1"\n',
        encoding="utf-8",
    )
    ext = TomlExtManifestReader().read(path)
    assert [s.name for s in ext.project] == ["a"]
    assert [s.name for s in ext.workspace] == ["w"]
    assert len(ext.notes) == 1
    assert "img" in ext.notes[0]


def test_ext_reader_degrades_on_bad_file(tmp_path: Path) -> None:
    ext = TomlExtManifestReader().read(tmp_path / "absent.toml")
    assert ext.project == ()
    assert len(ext.notes) == 1


def _config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "config.toml").write_text(
        '[[service]]\nname = "api"\ncmd = "x"\n[[service]]\nname = "fx"\nscope = "workspace"\ncmd = "y"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("WINTER_EXT_CONFIG_DIR", str(tmp_path))


def test_describe_and_catalog_emit_services(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _config(tmp_path, monkeypatch)
    for action in ("describe", "catalog"):
        assert cli.main([action]) == 0
        out = capsys.readouterr().out
        assert json.loads(out) == {"services": ["workspace/fx", "*/api"]}


def test_unknown_action_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WINTER_EXT_CONFIG_DIR", raising=False)
    assert cli.main(["bogus"]) == 2
    assert cli.main([]) == 2


def test_catalog_without_config_is_empty(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("WINTER_EXT_CONFIG_DIR", raising=False)
    monkeypatch.delenv("WINTER_WORKSPACE_DIR", raising=False)
    assert cli.main(["catalog"]) == 0
    assert json.loads(capsys.readouterr().out) == {"services": []}


def test_describe_without_manifest_emits_empty_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("WINTER_EXT_CONFIG_DIR", str(tmp_path))
    assert cli.main(["describe"]) == 0
    assert json.loads(capsys.readouterr().out) == {"services": []}


def test_describe_with_invalid_manifest_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "config.toml").write_text('[[service]]\nname = "a"\ncmd = ""\n', encoding="utf-8")
    monkeypatch.setenv("WINTER_EXT_CONFIG_DIR", str(tmp_path))
    assert cli.main(["describe"]) == 1


def test_down_and_up_of_a_missing_env_create_no_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    _config(config, monkeypatch)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setenv("WINTER_WORKSPACE_DIR", str(workspace))
    assert cli.main(["down", "__winter_verify/probe__"]) == 0
    assert "has no running instance" in capsys.readouterr().err
    assert cli.main(["up", "nosuchenv"]) == 1
    assert "env directory" in capsys.readouterr().err
    assert list(workspace.iterdir()) == []

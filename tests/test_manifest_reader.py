from __future__ import annotations

from pathlib import Path

import pytest

from process_compose_orchestrator.modules.manifest.errors import ManifestError
from process_compose_orchestrator.modules.manifest.internal.toml_manifest_reader import TomlManifestReader
from process_compose_orchestrator.modules.manifest.model import HealthType, RestartPolicy

# The winter-service-tmux workspace entries for the winter-test-service stack, verbatim.
TMUX_ENTRIES = """\
layout_hook = "layout-hook.sh"
workspace_layout_hook = "workspace-layout-hook.sh"

[[service]]
# Pane 0.0: FastAPI / uvicorn. Honors BOOT_DELAY_SECONDS; exposes chaos endpoints.
name = "api"
target = "0.0"
cmd = "cd winter-test-service && PYTHONPATH=.:api uv run python -m app"

[service.health]
# FastAPI readiness endpoint (api/app/main.py: GET /api/health). ${WTS_API_PORT}
# resolves per-env from the scope band injected on up/down/status.
type = "url"
target = "http://localhost:${WTS_API_PORT}/api/health"

[[service]]
# Pane 0.1: React + Vite dev server (proxies /api to the api service).
name = "web"
target = "0.1"
cmd = "cd winter-test-service/web && npm run dev"

[service.health]
# Vite dev server serves the app index at / once ready.
type = "url"
target = "http://localhost:${WTS_WEB_PORT}/"

[[service]]
# Pane 0.2: Python worker — steady heartbeat log stream + DB writes.
name = "worker"
target = "0.2"
cmd = "cd winter-test-service && uv run python -m worker.main"

[[service]]
name = "db-logs"
scope = "workspace"
target = "0.0"
cmd = "while true; do winter service logs workspace/db -f; sleep 1; done"
log = "pane"
"""


def _read(tmp_path: Path, text: str):
    (tmp_path / "config.toml").write_text(text, encoding="utf-8")
    return TomlManifestReader().read(tmp_path)


def test_tmux_entries_parse_clean(tmp_path: Path) -> None:
    manifest = _read(tmp_path, TMUX_ENTRIES)
    assert [s.name for s in manifest.services] == ["api", "web", "worker"]
    assert [s.name for s in manifest.workspace_services] == ["db-logs"]
    api = manifest.services[0]
    assert api.health is not None
    assert api.health.type is HealthType.URL
    assert api.health.target == "http://localhost:${WTS_API_PORT}/api/health"


def test_restart_table_parses(tmp_path: Path) -> None:
    manifest = _read(
        tmp_path,
        '[[service]]\nname = "a"\ncmd = "x"\n[service.restart]\npolicy = "on_failure"\n'
        "backoff_seconds = 1.5\nmax_restarts = 3\n",
    )
    restart = manifest.services[0].restart
    assert restart is not None
    assert (restart.policy, restart.backoff_seconds, restart.max_restarts) == (RestartPolicy.ON_FAILURE, 1.5, 3)


def test_command_alias_and_cwd_normalization(tmp_path: Path) -> None:
    manifest = _read(tmp_path, '[[service]]\nname = "a"\ncommand = "x"\ncwd = "./sub"\n')
    assert manifest.services[0].cmd == "x"
    assert manifest.services[0].cwd == "sub"


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ('name = "a"\ncmd = ""', "interactive"),
        ('name = "a"\ntarget = "1.1"', "interactive"),
        ('name = "a"\ncmd = "x"\n[service.health]\ntype = "log"\ntarget = "ready"', "health.type 'log'"),
        ('name = "a"\ncmd = "x"\n[service.health]\ntype = "uptime"\ntarget = "5s"', "health.type 'uptime'"),
        ('name = "a"\ncmd = "x"\ndepends_on = ["workspace/db"]', "cross-scope"),
    ],
)
def test_refusals_name_the_provider(tmp_path: Path, body: str, fragment: str) -> None:
    with pytest.raises(ManifestError) as info:
        _read(tmp_path, f"[[service]]\n{body}\n")
    assert fragment in str(info.value)
    assert "winter-service-process-compose" in str(info.value)


def test_workspace_service_may_qualify_its_own_scope(tmp_path: Path) -> None:
    manifest = _read(
        tmp_path,
        '[[service]]\nname = "a"\ncmd = "x"\nscope = "workspace"\n'
        '[[service]]\nname = "b"\ncmd = "x"\nscope = "workspace"\ndepends_on = ["workspace/a"]\n',
    )
    assert manifest.workspace_services[1].depends_on == ("a",)


def test_missing_and_malformed_files(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="not found"):
        TomlManifestReader().read(tmp_path)
    with pytest.raises(ManifestError, match="malformed TOML"):
        _read(tmp_path, "[[service")


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ('name = "a"\ncmd = "x"\n[service.restart]\npolicy = "sometimes"', "restart.policy"),
        ('name = "a"\ncmd = "x"\nscope = "galaxy"', "invalid scope"),
    ],
)
def test_invalid_values_are_rejected(tmp_path: Path, body: str, fragment: str) -> None:
    with pytest.raises(ManifestError, match=fragment):
        _read(tmp_path, f"[[service]]\n{body}\n")

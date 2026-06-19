import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.api.routes.plugin_guard import ensure_plugin_route_available, plugin_unavailable_http_error
from src.kernel.extensions import (
    PluginRuntime,
    PluginUnavailableError,
    build_agent_team_plugin_manifest,
    build_feedback_plugin_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_plugin_unavailable_http_error_prefers_exception_plugin_id() -> None:
    error = plugin_unavailable_http_error(
        "fallback_plugin",
        PluginUnavailableError("disabled", plugin_id="actual_plugin"),
    )

    assert error.status_code == 503
    assert error.detail == {
        "error": "plugin_unavailable",
        "plugin_id": "actual_plugin",
        "message": "disabled",
    }


def test_plugin_unavailable_http_error_uses_fallback_plugin_id() -> None:
    error = plugin_unavailable_http_error(
        "fallback_plugin",
        PluginUnavailableError("missing resource"),
    )

    assert error.status_code == 503
    assert error.detail == {
        "error": "plugin_unavailable",
        "plugin_id": "fallback_plugin",
        "message": "missing resource",
    }


def test_plugin_route_guard_rejects_disabled_feedback_runtime() -> None:
    runtime = PluginRuntime([build_feedback_plugin_manifest()])
    runtime.disable_plugin("feedback")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(plugin_runtime=runtime)))

    with pytest.raises(Exception) as exc_info:
        ensure_plugin_route_available(request, "feedback")

    error = exc_info.value
    assert getattr(error, "status_code", None) == 503
    assert getattr(error, "detail", None)["error"] == "plugin_unavailable"
    assert getattr(error, "detail", None)["plugin_id"] == "feedback"


def test_plugin_route_guard_rejects_disabled_agent_team_runtime() -> None:
    runtime = PluginRuntime([build_agent_team_plugin_manifest()])
    runtime.disable_plugin("agent_team")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(plugin_runtime=runtime)))

    with pytest.raises(Exception) as exc_info:
        ensure_plugin_route_available(request, "agent_team")

    error = exc_info.value
    assert getattr(error, "status_code", None) == 503
    assert getattr(error, "detail", None)["error"] == "plugin_unavailable"
    assert getattr(error, "detail", None)["plugin_id"] == "agent_team"


def test_agent_team_route_module_uses_router_level_plugin_guard() -> None:
    source = (PROJECT_ROOT / "src/api/routes/team.py").read_text(encoding="utf-8")

    assert "dependencies=[Depends(plugin_route_guard(AGENT_TEAM_PLUGIN_ID))]" in source
    assert "ensure_plugin_route_available" not in source


def test_plugin_declared_backend_route_modules_have_runtime_guards() -> None:
    route_modules: dict[str, set[str]] = {}
    for manifest_path in sorted(PROJECT_ROOT.glob("plugins/**/backend/plugin.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        plugin_id = manifest.get("plugin_id")
        for route in manifest.get("backend", {}).get("routes", []):
            module = route.get("module")
            if not plugin_id or not module:
                continue
            route_modules.setdefault(module, set()).add(plugin_id)

    assert route_modules, "backend plugin route declarations should exist"
    missing: list[dict[str, str]] = []
    for module, plugin_ids in route_modules.items():
        source_path = PROJECT_ROOT / Path(*module.split(".")).with_suffix(".py")
        if not source_path.exists():
            missing.extend(
                {"module": module, "plugin_id": plugin_id, "reason": "module_missing"}
                for plugin_id in sorted(plugin_ids)
            )
            continue
        source = source_path.read_text(encoding="utf-8")
        has_guard = "plugin_route_guard(" in source or "ensure_plugin_route_available(" in source
        if not has_guard:
            missing.extend(
                {"module": module, "plugin_id": plugin_id, "reason": "guard_missing"}
                for plugin_id in sorted(plugin_ids)
            )

    assert missing == []

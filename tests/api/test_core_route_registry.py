import asyncio
import io
import json
import sys
import zipfile
from pathlib import Path
from types import ModuleType

from fastapi import APIRouter, FastAPI
from starlette.testclient import TestClient

from src.api import deps as api_deps
from src.api.routes.registry import (
    CORE_ROUTE_REGISTRATIONS,
    CoreRouteRegistration,
    register_builtin_plugin_routes,
    register_core_routes,
    register_plugin_routes,
)
from src.infra.extensions import (
    InMemoryPluginRuntimeStateStorage,
    InMemoryPluginSettingsStorage,
    PluginSettingsService,
)
from src.kernel.config import settings
from src.kernel.extensions import (
    ADVANCED_FILE_VIEWERS_PLUGIN_ID,
    AGENT_TEAM_PLUGIN_ID,
    AUDIO_TRANSCRIPTION_PLUGIN_ID,
    BUILTIN_PLUGIN_MANIFESTS,
    FEEDBACK_PLUGIN_ID,
    FEISHU_CONNECTOR_ID,
    FEISHU_CONNECTOR_PLUGIN_ID,
    GITHUB_INSTALLER_PLUGIN_ID,
    IMAGE_GENERATION_PLUGIN_ID,
    USAGE_REPORTS_PLUGIN_ID,
    PluginManifest,
    PluginRuntime,
    PluginRuntimeStatus,
    core_route_ids_required_by_matrix,
)
from src.kernel.schemas.user import TokenPayload


def _plugin_runtime_reader() -> TokenPayload:
    return TokenPayload(
        sub="reader-1",
        username="reader",
        roles=["user"],
        permissions=["marketplace:read"],
    )


def _plugin_runtime_admin() -> TokenPayload:
    return TokenPayload(
        sub="admin-1",
        username="admin",
        roles=["admin"],
        permissions=["marketplace:read", "marketplace:admin", "settings:manage"],
    )


def test_core_route_registry_preserves_existing_registration_order():
    route_ids = [registration.id for registration in CORE_ROUTE_REGISTRATIONS]

    assert route_ids == [
        "health",
        "version",
        "chat",
        "agent",
        "agent_config",
        "agent_models",
        "auth",
        "users",
        "roles",
        "persona_presets",
        "sessions",
        "projects",
        "share",
        "skills",
        "marketplace",
        "plugin_runtime",
        "settings",
        "memory",
        "mcp",
        "mcp_admin",
        "env_vars",
        "upload",
        "files",
        "human",
        "notifications",
        "push",
        "channels",
        "scheduled_tasks",
        "websocket",
    ]


def test_core_route_registry_declares_key_core_prefixes_and_tags():
    by_id: dict[str, CoreRouteRegistration] = {
        registration.id: registration for registration in CORE_ROUTE_REGISTRATIONS
    }

    assert by_id["chat"].prefix == "/api/chat"
    assert by_id["sessions"].prefix == "/api/sessions"
    assert by_id["projects"].prefix == "/api/projects"
    assert by_id["mcp"].prefix == "/api/mcp"
    assert by_id["skills"].prefix == "/api/skills"
    assert by_id["memory"].prefix == "/api/memory"
    assert by_id["share"].prefix == "/api/share"
    assert by_id["upload"].prefix == "/api/upload"
    assert by_id["files"].prefix == "/api/files"
    assert by_id["human"].prefix == "/human"
    assert by_id["notifications"].prefix == "/api/notifications"
    assert by_id["push"].prefix == "/api/push"
    assert by_id["env_vars"].prefix == "/api/env-vars"
    assert by_id["marketplace"].prefix == "/api/marketplace"
    assert by_id["plugin_runtime"].prefix == "/api/extensions/plugins"
    assert "github" not in by_id
    assert by_id["scheduled_tasks"].tags == ("Scheduled Tasks",)


def test_register_core_routes_resolves_and_includes_declared_routers():
    first_router = APIRouter()
    second_router = APIRouter()

    @first_router.get("/first")
    async def first_route():
        return {"ok": True}

    @second_router.get("/second")
    async def second_route():
        return {"ok": True}

    first_module = ModuleType("tests.fake_first_route_module")
    second_module = ModuleType("tests.fake_second_route_module")
    first_module.router = first_router
    second_module.admin_router = second_router
    sys.modules[first_module.__name__] = first_module
    sys.modules[second_module.__name__] = second_module

    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "first",
                first_module.__name__,
                prefix="/api/first",
                tags=("First",),
            ),
            CoreRouteRegistration(
                "second",
                second_module.__name__,
                router_name="admin_router",
                prefix="/api/admin/second",
                tags=("Second",),
            ),
        ),
    )

    client = TestClient(app)

    assert client.get("/api/first/first").status_code == 200
    assert client.get("/api/admin/second/second").status_code == 200


def test_core_route_registry_declares_real_router_modules_without_eager_imports():
    by_id: dict[str, CoreRouteRegistration] = {
        registration.id: registration for registration in CORE_ROUTE_REGISTRATIONS
    }

    assert by_id["health"].module == "src.api.routes.health"
    assert by_id["agent_config"].module == "src.api.routes.agent.config"
    assert by_id["agent_models"].module == "src.api.routes.agent.model"
    assert by_id["mcp_admin"].module == "src.api.routes.mcp"
    assert by_id["mcp_admin"].router_name == "admin_router"
    assert by_id["marketplace"].module == "src.api.routes.marketplace"
    assert by_id["plugin_runtime"].module == "src.api.routes.plugin_runtime"


def test_core_stability_matrix_routes_exist_when_builtin_plugins_are_disabled() -> None:
    app = FastAPI()
    runtime = register_builtin_plugin_routes(app)
    runtime.disable_plugin(FEEDBACK_PLUGIN_ID)
    register_core_routes(app)
    by_id: dict[str, CoreRouteRegistration] = {
        registration.id: registration for registration in CORE_ROUTE_REGISTRATIONS
    }

    assert FEEDBACK_PLUGIN_ID not in core_route_ids_required_by_matrix()
    assert core_route_ids_required_by_matrix() <= set(by_id)
    assert runtime.get_state(FEEDBACK_PLUGIN_ID).status is PluginRuntimeStatus.DISABLED
    assert {route.plugin_id for route in runtime.routes()} == {
        AGENT_TEAM_PLUGIN_ID,
        USAGE_REPORTS_PLUGIN_ID,
        GITHUB_INSTALLER_PLUGIN_ID,
    }


def test_create_app_uses_core_route_registry_instead_of_inline_router_list():
    source = Path("src/api/main.py").read_text(encoding="utf-8")
    create_app_body = source.split("def create_app() -> FastAPI:", 1)[1].split(
        "# 创建应用实例",
        1,
    )[0]

    assert "register_core_routes(app)" in create_app_body
    assert "register_builtin_plugin_routes(app)" in create_app_body
    assert "app.include_router(" not in create_app_body


def test_feedback_shutdown_cleanup_is_owned_by_plugin_manifest() -> None:
    source = Path("src/api/main.py").read_text(encoding="utf-8")
    close_singletons_body = source.split(
        "async def _close_route_dependency_singletons() -> None:",
        1,
    )[1].split("\n\n", 1)[0]
    manifest = next(
        plugin for plugin in BUILTIN_PLUGIN_MANIFESTS if plugin.id == FEEDBACK_PLUGIN_ID
    )

    assert "close_feedback_manager" not in close_singletons_body
    assert [(hook.name, hook.module, hook.phase) for hook in manifest.lifespan_hooks] == [
        (
            "feedback:shutdown",
            "src.plugins.feedback.lifecycle:close_feedback_manager",
            "shutdown",
        )
    ]


def test_plugin_runtime_can_be_attached_to_scheduler_guard(monkeypatch) -> None:
    from src.api import main as api_main

    app = FastAPI()
    runtime = register_builtin_plugin_routes(app)
    attached = {}

    class _FakeScheduler:
        def set_plugin_runtime(self, value):
            attached["scheduler"] = value

    class _FakePubSubHub:
        def set_plugin_runtime(self, value):
            attached["pubsub"] = value

    monkeypatch.setattr(
        "src.infra.scheduler.runtime.get_runtime_scheduler",
        lambda: _FakeScheduler(),
    )
    monkeypatch.setattr("src.infra.pubsub_hub.get_pubsub_hub", lambda: _FakePubSubHub())

    api_main._attach_plugin_runtime_to_scheduler(app)

    assert attached["scheduler"] is runtime
    assert attached["pubsub"] is runtime


def test_plugin_runtime_lifecycle_hooks_are_executed_by_app_lifecycle_runner() -> None:
    from src.api import main as api_main

    calls: list[tuple[str, str, str]] = []

    def startup_hook(registration) -> None:
        calls.append((registration.plugin_id, registration.name, registration.phase))

    async def shutdown_hook(registration) -> None:
        calls.append((registration.plugin_id, registration.name, registration.phase))

    hook_module = ModuleType("tests.fake_plugin_lifecycle_hooks")
    hook_module.startup_hook = startup_hook
    hook_module.shutdown_hook = shutdown_hook
    sys.modules[hook_module.__name__] = hook_module

    app = FastAPI()
    app.state.plugin_runtime = PluginRuntime(
        [
            PluginManifest(
                id="hooked",
                name="Hooked",
                version="1.0.0",
                api_version="v1",
                permissions=["hooked:read"],
                lifespan_hooks=[
                    {
                        "name": "hooked-startup",
                        "module": f"{hook_module.__name__}:startup_hook",
                        "phase": "startup",
                    },
                    {
                        "name": "hooked-shutdown",
                        "module": f"{hook_module.__name__}:shutdown_hook",
                        "phase": "shutdown",
                    },
                ],
            )
        ]
    )

    source = Path("src/api/main.py").read_text(encoding="utf-8")
    assert 'await _run_plugin_lifecycle_hooks(app, "startup")' in source
    assert 'await _run_plugin_lifecycle_hooks(app, "shutdown")' in source

    asyncio.run(api_main._run_plugin_lifecycle_hooks(app, "startup"))
    asyncio.run(api_main._run_plugin_lifecycle_hooks(app, "shutdown"))

    assert ("hooked", "hooked-startup", "startup") in calls
    assert ("hooked", "hooked-shutdown", "shutdown") in calls
    results = app.state.plugin_runtime_hook_results
    assert [(result.hook_name, result.status) for result in results] == [
        ("hooked-startup", "succeeded"),
        ("hooked-shutdown", "succeeded"),
    ]


def test_plugin_runtime_lifecycle_hook_failures_do_not_block_app_lifecycle_runner() -> None:
    from src.api import main as api_main

    def broken_hook() -> None:
        raise RuntimeError("broken startup hook")

    hook_module = ModuleType("tests.fake_broken_plugin_lifecycle_hooks")
    hook_module.broken_hook = broken_hook
    sys.modules[hook_module.__name__] = hook_module

    runtime = PluginRuntime(
        [
            PluginManifest(
                id="broken_hook_plugin",
                name="Broken Hook Plugin",
                version="1.0.0",
                api_version="v1",
                permissions=["broken_hook_plugin:read"],
                lifespan_hooks=[
                    {
                        "name": "broken-startup",
                        "module": f"{hook_module.__name__}:broken_hook",
                        "phase": "startup",
                    }
                ],
            )
        ]
    )
    app = FastAPI()
    app.state.plugin_runtime = runtime

    asyncio.run(api_main._run_plugin_lifecycle_hooks(app, "startup"))

    state = runtime.get_state("broken_hook_plugin")
    assert state.status is PluginRuntimeStatus.ERROR
    assert state.issues[-1].code == "hook_failed"
    assert app.state.plugin_runtime_hook_results[0].status == "failed"


def test_feedback_usage_reports_and_github_installer_are_registered_as_builtin_plugin_routes_not_core_routes() -> None:
    app = FastAPI()
    runtime = register_builtin_plugin_routes(app)
    feedback_state = runtime.get_state(FEEDBACK_PLUGIN_ID)
    usage_state = runtime.get_state(USAGE_REPORTS_PLUGIN_ID)
    github_state = runtime.get_state(GITHUB_INSTALLER_PLUGIN_ID)
    core_route_ids = {registration.id for registration in CORE_ROUTE_REGISTRATIONS}

    assert "feedback" not in core_route_ids
    assert "usage" not in core_route_ids
    assert "github" not in core_route_ids
    assert "teams" not in core_route_ids
    assert feedback_state is not None
    assert feedback_state.status is PluginRuntimeStatus.ENABLED
    assert usage_state is not None
    assert usage_state.status is PluginRuntimeStatus.ENABLED
    assert github_state is not None
    assert github_state.status is PluginRuntimeStatus.ENABLED
    assert {
        (route.plugin_id, route.prefix)
        for route in runtime.routes()
    } >= {
        (FEEDBACK_PLUGIN_ID, "/api/feedback"),
        (AGENT_TEAM_PLUGIN_ID, "/api/teams"),
        (USAGE_REPORTS_PLUGIN_ID, "/api/usage"),
        (GITHUB_INSTALLER_PLUGIN_ID, "/api/github"),
    }
    assert app.state.plugin_runtime is runtime


def test_plugin_runtime_routes_expose_feedback_observability() -> None:
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    runtime = register_builtin_plugin_routes(app)
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_reader

    response = TestClient(app).get("/api/extensions/plugins/")

    assert response.status_code == 200
    payload = response.json()
    runtime_capabilities = {
        key: value
        for key, value in payload["runtime"].items()
        if key
        not in {
            "acceptance_matrix",
            "phase_progress",
            "feedback_migration",
        }
    }
    assert runtime_capabilities | {"guard_surfaces": []} == {
        "api_versions": ["v1"],
        "mode": "local_folder_packages_with_static_compat",
        "supports_hot_install": False,
        "supports_remote_packages": False,
        "supports_local_folder_packages": True,
        "supports_plugin_data_dir": True,
        "supports_package_integrity": True,
        "requires_signed_user_installed_enable": True,
        "supports_physical_uninstall": True,
        "supports_uninstall_dry_run_validation": True,
        "supports_remote_package_import": False,
        "supports_state_persistence": True,
        "supports_audit": True,
        "guard_surfaces": [],
    }
    guard_surfaces = {surface["id"]: surface for surface in payload["runtime"]["guard_surfaces"]}
    assert {
        "route_guard",
        "tool_guard",
        "scheduler_guard",
        "listener_guard",
        "uninstall_guard",
        "hot_install_guard",
        "package_integrity_guard",
    } <= set(guard_surfaces)
    assert guard_surfaces["route_guard"]["status"] == "enforced"
    assert guard_surfaces["tool_guard"]["failure_mode"] == "fail_closed"
    assert guard_surfaces["scheduler_guard"]["enforced"] is True
    assert guard_surfaces["listener_guard"]["enforced"] is True
    assert guard_surfaces["uninstall_guard"]["status"] == "controlled_execution"
    assert guard_surfaces["hot_install_guard"]["status"] == "blocked"
    assert guard_surfaces["package_integrity_guard"]["failure_mode"] == "unsigned_enable_blocked"
    feedback = next(plugin for plugin in payload["plugins"] if plugin["plugin_id"] == FEEDBACK_PLUGIN_ID)
    assert feedback["package"]["source_type"] == "system"
    assert feedback["package"]["manifest_authority"] == "folder_package"
    assert feedback["package"]["static_fallback_used"] is False
    assert feedback["package"]["static_fallback_fields"] == []
    assert feedback["package"]["source_path"].endswith("plugins\\system\\feedback") or feedback["package"]["source_path"].endswith("plugins/system/feedback")
    assert feedback["package"]["data_dir"].endswith("plugin-data\\feedback") or feedback["package"]["data_dir"].endswith("plugin-data/feedback")
    assert feedback["package"]["layout"]["has_data_template"] is True
    assert feedback["package"]["data_template"]["exists"] is True
    assert "state/audit.jsonl" in feedback["package"]["data_template"]["files"]
    acceptance_matrix = payload["runtime"]["acceptance_matrix"]
    assert acceptance_matrix["passed"] is True
    assert acceptance_matrix["total"] == 11
    assert acceptance_matrix["passed_count"] == 11
    assert acceptance_matrix["missing"] == []
    assert set(acceptance_matrix["sections"]) == {
        "core_stability",
        "plugin_runtime",
        "extension_center_boundary",
        "disabled_semantics",
        "resource_ledger_and_dry_run",
        "feedback_migration",
    }
    assert any(
        item["requirement_id"] == "feedback_first_migration_gates_pass"
        and item["passed"] is True
        for item in acceptance_matrix["requirements"]
    )
    phase_progress = payload["runtime"]["phase_progress"]
    assert {phase["phase"] for phase in phase_progress} == {
        "phase_1_runtime_foundation",
        "phase_2_resource_dry_run",
        "phase_2_core_plugin_matrix",
        "phase_3_feedback_first_step",
    }
    assert all(phase["passed"] is True for phase in phase_progress)
    feedback_migration = payload["runtime"]["feedback_migration"]
    assert feedback_migration["plugin_id"] == FEEDBACK_PLUGIN_ID
    assert feedback_migration["ready_for_first_migration_step"] is True
    assert feedback_migration["missing_gates"] == []
    assert len(feedback_migration["gate_evidence"]) == 8
    assert all(gate["passed"] is True for gate in feedback_migration["gate_evidence"])
    assert payload["total"] == 8
    plugins_by_id = {plugin["plugin_id"]: plugin for plugin in payload["plugins"]}
    assert all(
        plugin["package"]["manifest_authority"] == "folder_package"
        for plugin in plugins_by_id.values()
    )
    assert all(
        plugin["package"]["static_fallback_used"] is False
        for plugin in plugins_by_id.values()
    )
    feedback = plugins_by_id[FEEDBACK_PLUGIN_ID]
    assert feedback["plugin_id"] == FEEDBACK_PLUGIN_ID
    assert feedback["status"] == "enabled"
    assert feedback["executable"] is True
    assert feedback["routes"][0]["prefix"] == "/api/feedback"
    assert feedback["tools"] == [
        {
            "name": "feedback.summary",
            "module": "src.plugins.feedback.tools",
            "required_permissions": ["feedback:read"],
            "legacy_ids": [],
        }
    ]
    assert feedback["frontend"]["routes"] == ["feedback-route"]
    assert feedback["frontend"]["message_actions"] == ["feedback:message-feedback"]
    assert feedback["runtime_side_effect"] == {
        "action": "none",
        "status": "not_applicable",
        "message": "No runtime side effect is registered for this static plugin.",
    }
    assert feedback["resource_types"]["db_collection"] == 1
    assert feedback["resource_types"]["db_index"] == 4
    assert feedback["resource_types"]["message_action"] == 1
    assert feedback["resource_types"]["tool"] == 1
    assert feedback["dry_run_actions"] == {"archive": 8, "keep": 11}
    agent_team = plugins_by_id[AGENT_TEAM_PLUGIN_ID]
    assert agent_team["status"] == "enabled"
    assert agent_team["routes"][0]["prefix"] == "/api/teams"
    assert agent_team["frontend"]["routes"] == ["agent_team:team-route"]
    assert agent_team["frontend"]["nav_items"] == ["agent_team:team-nav"]
    assert agent_team["frontend"]["tool_renderers"] == ["agent_team:agent-team"]
    assert {tool["name"] for tool in agent_team["tools"]} == {
        "agent_team.search_persona_presets",
        "agent_team.create_agent_team",
    }
    assert agent_team["resource_types"]["backend_route"] == 1
    assert agent_team["resource_types"]["tool"] == 2
    assert agent_team["resource_types"]["db_collection"] == 1
    assert agent_team["resource_types"]["db_document"] == 2
    image_generation = plugins_by_id[IMAGE_GENERATION_PLUGIN_ID]
    assert image_generation["status"] in {"enabled", "disabled"}
    assert image_generation["tools"] == [
        {
            "name": "image_generate",
            "module": "src.infra.tool.image_generation_tool",
            "required_permissions": ["mcp:read"],
            "legacy_ids": ["image_generate"],
        }
    ]
    assert image_generation["frontend"]["tool_renderers"] == [
        "image_generation:image-generate"
    ]
    assert image_generation["resource_types"]["tool"] == 1
    assert image_generation["resource_types"]["tool_renderer"] == 1
    assert image_generation["resource_types"]["setting"] == 4
    assert image_generation["resource_types"]["env_key_declaration"] == 1
    audio_transcription = plugins_by_id[AUDIO_TRANSCRIPTION_PLUGIN_ID]
    assert audio_transcription["status"] in {"enabled", "disabled"}
    assert audio_transcription["tools"] == [
        {
            "name": "audio_transcribe",
            "module": "src.infra.tool.audio_transcribe_tool",
            "required_permissions": ["mcp:read"],
            "legacy_ids": ["audio_transcribe"],
        }
    ]
    assert audio_transcription["frontend"]["tool_renderers"] == [
        "audio_transcription:audio-transcribe"
    ]
    assert audio_transcription["resource_types"]["tool"] == 1
    assert audio_transcription["resource_types"]["tool_renderer"] == 1
    assert audio_transcription["resource_types"]["setting"] == 4
    assert audio_transcription["resource_types"]["env_key_declaration"] == 1
    usage_reports = plugins_by_id[USAGE_REPORTS_PLUGIN_ID]
    assert usage_reports["status"] == "enabled"
    assert usage_reports["routes"][0]["prefix"] == "/api/usage"
    assert usage_reports["frontend"]["routes"] == ["usage_reports:usage-route"]
    assert usage_reports["frontend"]["panels"] == ["usage_reports:usage-panel"]
    assert usage_reports["frontend"]["nav_items"] == ["usage_reports:usage-menu"]
    assert usage_reports["resource_types"]["backend_route"] == 1
    assert usage_reports["resource_types"]["frontend_route"] == 1
    assert usage_reports["resource_types"]["panel"] == 1
    assert usage_reports["resource_types"]["nav_item"] == 1
    assert usage_reports["resource_types"]["permission"] == 2
    assert usage_reports["resource_types"]["db_collection"] == 1
    assert usage_reports["resource_types"]["db_index"] == 4
    advanced_file_viewers = plugins_by_id[ADVANCED_FILE_VIEWERS_PLUGIN_ID]
    assert advanced_file_viewers["status"] == "enabled"
    assert advanced_file_viewers["routes"] == []
    assert advanced_file_viewers["tools"] == []
    assert advanced_file_viewers["frontend"]["file_viewers"] == [
        "advanced_file_viewers:pdf",
        "advanced_file_viewers:ppt",
        "advanced_file_viewers:word",
        "advanced_file_viewers:excel",
        "advanced_file_viewers:cad",
        "advanced_file_viewers:excalidraw",
        "advanced_file_viewers:html",
        "advanced_file_viewers:markdown",
        "advanced_file_viewers:code",
    ]
    assert advanced_file_viewers["resource_types"]["file_viewer"] == 9
    assert advanced_file_viewers["resource_types"]["cache_key"] == 1
    assert advanced_file_viewers["resource_types"]["file"] == 1
    github_installer = plugins_by_id[GITHUB_INSTALLER_PLUGIN_ID]
    assert github_installer["status"] == "enabled"
    assert github_installer["routes"][0]["prefix"] == "/api/github"
    assert github_installer["frontend"]["skill_importers"] == [
        "github_installer:github-import"
    ]
    assert github_installer["resource_types"]["backend_route"] == 1
    assert github_installer["resource_types"]["skill_importer"] == 1
    assert github_installer["resource_types"]["permission"] == 2
    assert github_installer["resource_types"]["cache_key"] == 1
    assert github_installer["resource_types"]["file"] == 1
    feishu_connector = plugins_by_id[FEISHU_CONNECTOR_PLUGIN_ID]
    assert feishu_connector["status"] == "enabled"
    assert feishu_connector["routes"] == []
    assert feishu_connector["tools"] == []
    assert feishu_connector["frontend"]["channel_connectors"] == [FEISHU_CONNECTOR_ID]
    assert feishu_connector["runtime_side_effect"] == {
        "action": "none",
        "status": "available",
        "message": "Feishu connector start/stop side effects are available during runtime state changes.",
    }
    assert feishu_connector["resource_types"]["channel_connector"] == 1
    assert feishu_connector["resource_types"]["listener"] == 1
    assert feishu_connector["resource_types"]["db_document"] == 1
    assert feishu_connector["resource_types"]["db_index"] == 1
    assert feishu_connector["resource_types"]["cache_key"] == 2
    assert feishu_connector["resource_types"]["file"] == 1
    assert runtime.get_state(FEEDBACK_PLUGIN_ID) is not None


def test_plugin_runtime_settings_api_exposes_plugin_owned_settings() -> None:
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    register_builtin_plugin_routes(app)
    app.state.plugin_settings_service = PluginSettingsService(
        storage=InMemoryPluginSettingsStorage()
    )
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_admin
    client = TestClient(app)

    response = client.get(f"/api/extensions/plugins/{IMAGE_GENERATION_PLUGIN_ID}/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["plugin_id"] == IMAGE_GENERATION_PLUGIN_ID
    assert payload["migration_status"]["runtime_state_controls_enablement"] is True
    settings_by_key = {item["key"]: item for item in payload["settings"]}
    assert set(settings_by_key) == {"API_KEY", "BASE_URL", "MODEL", "TIMEOUT"}
    assert settings_by_key["API_KEY"]["qualified_key"] == "image_generation.API_KEY"
    assert settings_by_key["API_KEY"]["sensitive"] is True
    assert settings_by_key["API_KEY"]["legacy_system_setting_keys"] == [
        "IMAGE_GENERATION_API_KEY"
    ]
    assert settings_by_key["BASE_URL"]["source"].startswith("legacy:") or settings_by_key[
        "BASE_URL"
    ]["source"] in {"env:IMAGE_GENERATION_BASE_URL", "default"}

    updated = client.put(
        f"/api/extensions/plugins/{IMAGE_GENERATION_PLUGIN_ID}/settings/MODEL",
        json={"value": "custom-image-model"},
    )

    assert updated.status_code == 200
    updated_settings = {item["key"]: item for item in updated.json()["settings"]}
    assert updated_settings["MODEL"]["value"] == "custom-image-model"
    assert updated_settings["MODEL"]["source"] == "manual"


def test_plugin_owned_system_settings_are_not_exposed_as_global_settings() -> None:
    from src.infra.extensions import plugin_owned_system_setting_keys

    owned = plugin_owned_system_setting_keys(BUILTIN_PLUGIN_MANIFESTS)

    assert owned["IMAGE_GENERATION_API_KEY"] == IMAGE_GENERATION_PLUGIN_ID
    assert owned["AUDIO_TRANSCRIPTION_API_KEY"] == AUDIO_TRANSCRIPTION_PLUGIN_ID


def test_plugin_runtime_contribution_states_are_minimal_and_public_safe() -> None:
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    register_builtin_plugin_routes(app)

    response = TestClient(app).get("/api/extensions/plugins/contribution-states")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 8
    plugins_by_id = {plugin["plugin_id"]: plugin for plugin in payload["plugins"]}
    assert set(plugins_by_id) == {
        FEEDBACK_PLUGIN_ID,
        AGENT_TEAM_PLUGIN_ID,
        IMAGE_GENERATION_PLUGIN_ID,
        AUDIO_TRANSCRIPTION_PLUGIN_ID,
        USAGE_REPORTS_PLUGIN_ID,
        ADVANCED_FILE_VIEWERS_PLUGIN_ID,
        GITHUB_INSTALLER_PLUGIN_ID,
        FEISHU_CONNECTOR_PLUGIN_ID,
    }
    assert set(plugins_by_id[FEEDBACK_PLUGIN_ID]) == {
        "plugin_id",
        "enabled",
        "executable",
        "status",
    }
    assert plugins_by_id[FEEDBACK_PLUGIN_ID]["enabled"] is True
    assert plugins_by_id[FEEDBACK_PLUGIN_ID]["executable"] is True


def test_plugin_runtime_response_includes_state_source_metadata() -> None:
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    register_builtin_plugin_routes(app)
    storage = InMemoryPluginRuntimeStateStorage()
    app.state.plugin_runtime_state_storage = storage
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_reader

    response = TestClient(app).get(f"/api/extensions/plugins/{FEEDBACK_PLUGIN_ID}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state_source"] == "manifest_default"
    assert payload["state_updated_at"] is None
    assert payload["state_updated_by"] is None


def test_plugin_runtime_resource_and_dry_run_detail_routes() -> None:
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    register_builtin_plugin_routes(app)
    storage = InMemoryPluginRuntimeStateStorage()
    app.state.plugin_runtime_state_storage = storage
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_reader
    client = TestClient(app)

    resources = client.get(f"/api/extensions/plugins/{FEEDBACK_PLUGIN_ID}/resources")
    dry_run = client.get(
        f"/api/extensions/plugins/{FEEDBACK_PLUGIN_ID}/uninstall-dry-run"
    )

    assert resources.status_code == 200
    resource_payload = resources.json()
    assert resource_payload["total"] == 19
    assert resource_payload["resource_types"]["message_action"] == 1
    assert resource_payload["resource_types"]["plugin_package_folder"] == 1
    assert resource_payload["resource_types"]["plugin_data_folder"] == 1
    assert any(
        item["resource_id"] == "feedback:message-feedback"
        and item["resource_type"] == "message_action"
        and item["cleanup_strategy"] == "keep"
        for item in resource_payload["resources"]
    )
    assert any(
        item["resource_id"] == "feedback"
        and item["resource_type"] == "db_collection"
        and item["cleanup_strategy"] == "keep"
        for item in resource_payload["resources"]
    )
    assert any(
        item["resource_id"] == "feedback.summary"
        and item["resource_type"] == "tool"
        and item["cleanup_strategy"] == "keep"
        for item in resource_payload["resources"]
    )

    assert dry_run.status_code == 200
    dry_run_payload = dry_run.json()
    assert dry_run_payload["resource_count"] == 19
    assert dry_run_payload["snapshot_id"]
    assert dry_run_payload["resource_fingerprint"]
    assert dry_run_payload["expires_at"] > dry_run_payload["created_at"]
    assert dry_run_payload["actions"] == {"archive": 8, "keep": 11}
    dry_run_resources = dry_run_payload["resources"]
    assert any(
        item["resource_type"] == "plugin_package_folder"
        and item["action"] == "archive"
        and item["metadata"]["source_type"] == "system"
        for item in dry_run_resources
    )
    assert any(
        item["resource_type"] == "plugin_data_folder"
        and item["action"] == "keep"
        and item["metadata"]["data_policy"] == "plugin-data is retained by default"
        for item in dry_run_resources
    )
    assert any(
        item["resource_type"] == "plugin_data_config"
        and item["action"] == "keep"
        and "plugin_settings" in item["metadata"]["sensitive_policy"]
        for item in dry_run_resources
    )
    assert any(
        item["resource_type"] == "plugin_data_storage"
        and item["action"] == "keep"
        for item in dry_run_resources
    )
    assert dry_run_payload["package_data_policy"] == {
        "package_folder_action": "archive",
        "plugin_data_folder_action": "keep",
        "plugin_data_config_action": "keep",
        "plugin_data_storage_action": "keep",
        "frontend_asset_action": None,
        "runtime_data_delete_allowed": False,
        "sensitive_settings_delete_allowed": False,
        "requires_physical_data_delete_confirmation": False,
        "default_retention": "keep_user_data",
        "protected_resource_types": [
            "plugin_data_config",
            "plugin_data_folder",
            "plugin_data_storage",
        ],
        "notes": [
            "Plugin package folders may be archived by uninstall workflows.",
            "plugin-data is retained by default and is never physically deleted by dry-run.",
            "Sensitive plugin settings remain masked and require separate manual review.",
        ],
    }
    assert dry_run_payload["validation"]["allowed"] is True
    assert dry_run_payload["validation"]["blockers"] == []
    assert dry_run_payload["validation"]["supports_physical_uninstall"] is True
    assert dry_run_payload["rollback_notes"] == [
        "Uninstall execution must use this dry-run snapshot and only process plugin-owned resources."
    ]
    assert not dry_run_payload["requires_confirmation"]


def test_plugin_runtime_package_and_data_routes() -> None:
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    storage = InMemoryPluginRuntimeStateStorage()
    app.state.plugin_runtime_state_storage = storage
    register_builtin_plugin_routes(app)
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_admin
    client = TestClient(app)

    packages = client.get("/api/extensions/plugins/packages")
    scan = client.post("/api/extensions/plugins/packages/scan")
    data = client.get(f"/api/extensions/plugins/{FEEDBACK_PLUGIN_ID}/data")
    package_export = client.get(f"/api/extensions/plugins/{FEEDBACK_PLUGIN_ID}/package-export")

    assert packages.status_code == 200
    assert packages.json()["total"] == 8
    assert any(item["plugin_id"] == FEEDBACK_PLUGIN_ID and item["valid"] for item in packages.json()["packages"])
    assert scan.status_code == 200
    assert scan.json()["total"] == 8
    assert data.status_code == 200
    assert data.json()["data_dir"].endswith("plugin-data\\feedback") or data.json()["data_dir"].endswith("plugin-data/feedback")
    assert "config" in data.json()["subdirs"]
    assert package_export.status_code == 200
    package_payload = package_export.json()
    assert package_payload["schema_version"] == "lambchat.plugin.package-export.v1"
    assert package_payload["source_type"] == "system"
    assert package_payload["package_summary"]["manifest_authority"] == "folder_package"
    assert package_payload["package_summary"]["static_fallback_used"] is False
    assert package_payload["package_summary"]["static_fallback_fields"] == []
    assert package_payload["package_summary"]["data_policy"] == {
        "runtime_data_in_archive": False,
        "snapshot_metadata_in_export": True,
        "default_retention": "keep_user_data",
        "data_dir": package_payload["data_dir"],
        "sensitive_settings_included": False,
        "notes": [
            "plugin-data runtime files are not bundled in package archives.",
            "package-export includes plugin-data snapshot metadata only.",
            "sensitive plugin settings remain masked and are not written into plugin-data archives.",
        ],
    }
    assert package_payload["package_summary"]["layout"]["has_config_schema"] is True
    assert package_payload["package_summary"]["layout"]["has_resources"] is True
    assert package_payload["package_summary"]["layout"]["has_data_template"] is True
    assert package_payload["package_summary"]["data_template"]["exists"] is True
    assert "state/audit.jsonl" in package_payload["package_summary"]["data_template"]["files"]
    assert package_payload["package_summary"]["standard_files"]["plugin.yaml"] is True
    assert package_payload["package_summary"]["standard_files"]["config/schema.json"] is True
    assert package_payload["package_summary"]["standard_files"]["resources/resources.yaml"] is True
    assert "plugin.yaml" in package_payload["package_summary"]["top_level_entries"]
    assert package_payload["data_snapshot"]["plugin_id"] == FEEDBACK_PLUGIN_ID


def test_plugin_runtime_data_reset_backs_up_current_config(tmp_path: Path, monkeypatch) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    source = tmp_path / "incoming" / "data_plugin"
    source.mkdir(parents=True)
    (source / "plugin.yaml").write_text(
        """
id: data_plugin
name: Data Plugin
version: 1.0.0
api_version: v1
enabled_by_default: false
settings: []
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "PLUGIN_PACKAGE_PATH", str(plugin_root))
    monkeypatch.setattr(settings, "PLUGIN_DATA_PATH", str(data_root))
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    storage = InMemoryPluginRuntimeStateStorage()
    app.state.plugin_runtime_state_storage = storage
    register_builtin_plugin_routes(app)
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_admin
    client = TestClient(app)

    imported = client.post(
        "/api/extensions/plugins/packages/import",
        json={"source_path": str(source), "dry_run": False},
    )
    assert imported.status_code == 200
    current_path = data_root / "data_plugin" / "config" / "current.json"
    current_path.write_text('{"limit": 7}\n', encoding="utf-8")

    reset = client.post("/api/extensions/plugins/data_plugin/data/reset")

    assert reset.status_code == 200
    payload = reset.json()
    assert payload["backup_count"] == 1
    assert payload["last_backup_path"]
    assert current_path.read_text(encoding="utf-8") == "{}\n"
    assert Path(payload["last_backup_path"]).read_text(encoding="utf-8") == '{"limit": 7}\n'
    assert storage.audit_records[-1].action == "plugin_data_reset"
    assert storage.audit_records[-1].actor_user_id == "admin-1"
    audit = client.get("/api/extensions/plugins/data_plugin/audit")
    assert audit.status_code == 200
    assert audit.json()["audit"][0]["action"] == "plugin_data_reset"


def test_builtin_folder_package_is_authoritative_for_feedback_runtime() -> None:
    static_stub = PluginManifest(
        id=FEEDBACK_PLUGIN_ID,
        name="Feedback Static Stub",
        version="0.0.0",
        api_version="v1",
        permissions=["feedback:read"],
        enabled_by_default=True,
        install_type=BUILTIN_PLUGIN_MANIFESTS[0].install_type,
    )
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    runtime = register_builtin_plugin_routes(app, manifests=(static_stub,))
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_admin
    client = TestClient(app)

    feedback = client.get("/api/extensions/plugins/").json()["plugins"][0]

    assert runtime.get_state(FEEDBACK_PLUGIN_ID).manifest is not None
    assert runtime.get_state(FEEDBACK_PLUGIN_ID).manifest.name == "Feedback"
    assert feedback["name"] == "Feedback"
    assert feedback["package"]["source_type"] == "system"
    assert feedback["package"]["manifest_authority"] == "folder_package"
    assert feedback["package"]["static_fallback_used"] is False
    assert feedback["routes"][0]["prefix"] == "/api/feedback"
    assert feedback["tools"][0]["name"] == "feedback.summary"
    assert feedback["frontend"]["routes"] == ["feedback-route"]
    assert feedback["depends_on"] == []
    assert feedback["resource_types"]["db_index"] == 4
    assert feedback["resource_types"]["message_action"] == 1


def test_plugin_runtime_package_export_includes_plugin_defaults() -> None:
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    app.state.plugin_runtime_state_storage = InMemoryPluginRuntimeStateStorage()
    register_builtin_plugin_routes(app)
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_admin

    response = TestClient(app).get(
        f"/api/extensions/plugins/{IMAGE_GENERATION_PLUGIN_ID}/package-export"
    )

    assert response.status_code == 200
    summary = response.json()["package_summary"]
    assert summary["layout"]["has_config_schema"] is True
    assert summary["layout"]["has_config_defaults"] is True
    assert summary["layout"]["has_resources"] is True
    assert summary["config_defaults"] == {
        "API_KEY": "",
        "BASE_URL": "https://api.openai.com/v1",
        "MODEL": "gpt-image-2",
        "TIMEOUT": 120,
    }
    assert summary["standard_files"]["config/defaults.json"] is True
    assert summary["file_count"] >= 4
    assert summary["integrity"]["algorithm"] == "sha256:sorted-file-list-v1"
    assert len(summary["integrity"]["package_sha256"]) == 64
    assert summary["integrity"]["signature_status"] == "unsigned"


def test_plugin_runtime_package_archive_download_contains_folder_package_only() -> None:
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    app.state.plugin_runtime_state_storage = InMemoryPluginRuntimeStateStorage()
    register_builtin_plugin_routes(app)
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_admin

    response = TestClient(app).get(
        f"/api/extensions/plugins/{IMAGE_GENERATION_PLUGIN_ID}/package-archive"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    assert "image_generation-plugin-package.zip" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert "image_generation/plugin.yaml" in names
        assert "image_generation/config/schema.json" in names
        assert "image_generation/config/defaults.json" in names
        assert "image_generation/resources/resources.yaml" in names
        assert "image_generation/package-summary.json" in names
        assert all(not name.startswith("plugin-data/") for name in names)
        summary = json.loads(archive.read("image_generation/package-summary.json"))
    assert summary["schema_version"] == "lambchat.plugin.package-summary.v1"
    assert summary["plugin_id"] == IMAGE_GENERATION_PLUGIN_ID
    assert summary["manifest_authority"] == "folder_package"
    assert summary["static_fallback_used"] is False
    assert summary["static_fallback_fields"] == []
    assert summary["data_policy"]["runtime_data_in_archive"] is False
    assert summary["data_policy"]["snapshot_metadata_in_export"] is True
    assert summary["data_policy"]["sensitive_settings_included"] is False
    assert summary["package_summary"]["config_defaults"]["MODEL"] == "gpt-image-2"


def test_plugin_runtime_package_import_route_stages_local_folder_and_defaults_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    source = tmp_path / "incoming" / "folder_plugin"
    source.mkdir(parents=True)
    (source / "plugin.yaml").write_text(
        """
id: folder_plugin
name: Folder Plugin
version: 1.0.0
api_version: v1
enabled_by_default: false
settings:
  - key: LIMIT
    type: number
    default: 3
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "PLUGIN_PACKAGE_PATH", str(plugin_root))
    monkeypatch.setattr(settings, "PLUGIN_DATA_PATH", str(data_root))
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    storage = InMemoryPluginRuntimeStateStorage()
    app.state.plugin_runtime_state_storage = storage
    app.state.plugin_settings_service = PluginSettingsService(
        storage=InMemoryPluginSettingsStorage()
    )
    register_builtin_plugin_routes(app)
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_admin
    client = TestClient(app)

    dry_run = client.post(
        "/api/extensions/plugins/packages/import",
        json={"source_path": str(source), "dry_run": True},
    )
    assert dry_run.status_code == 200
    assert dry_run.json()["status"] == "validated"
    assert dry_run.json()["dry_run"] is True
    assert not (plugin_root / "installed" / "folder_plugin").exists()

    installed = client.post(
        "/api/extensions/plugins/packages/import",
        json={"source_path": str(source), "dry_run": False},
    )
    packages = client.get("/api/extensions/plugins/packages")
    runtime_list = client.get("/api/extensions/plugins/")
    settings_response = client.get("/api/extensions/plugins/folder_plugin/settings")
    data_response = client.get("/api/extensions/plugins/folder_plugin/data")

    assert installed.status_code == 200
    assert installed.json()["status"] == "installed"
    assert installed.json()["dry_run"] is False
    assert (plugin_root / "installed" / "folder_plugin" / "plugin.yaml").is_file()
    assert (data_root / "folder_plugin" / "config" / "defaults.json").is_file()
    assert storage.overrides["folder_plugin"].status is PluginRuntimeStatus.DISABLED
    assert storage.audit_records[-1].action == "package_import"
    assert packages.status_code == 200
    assert any(item["plugin_id"] == "folder_plugin" for item in packages.json()["packages"])
    assert runtime_list.status_code == 200
    runtime_plugin = next(item for item in runtime_list.json()["plugins"] if item["plugin_id"] == "folder_plugin")
    assert runtime_plugin["status"] == "disabled"
    assert runtime_plugin["executable"] is False
    assert runtime_plugin["install_type"] == "user_installed"
    assert runtime_plugin["package"]["source_type"] == "installed"
    assert settings_response.status_code == 200
    assert settings_response.json()["settings"][0]["key"] == "LIMIT"
    assert data_response.status_code == 200
    assert data_response.json()["plugin_id"] == "folder_plugin"


def test_plugin_frontend_dist_assets_are_served_with_runtime_guard(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    plugin_folder = plugin_root / "installed" / "asset_plugin"
    dist_dir = plugin_folder / "frontend" / "dist"
    dist_dir.mkdir(parents=True)
    (plugin_folder / "plugin.yaml").write_text(
        """
id: asset_plugin
name: Asset Plugin
version: 1.0.0
api_version: v1
enabled_by_default: true
permissions:
  - asset_plugin:read
frontend:
  panels:
    - asset_plugin:panel
""",
        encoding="utf-8",
    )
    (dist_dir / "widget.js").write_bytes(b"export const value = 1;\n")
    monkeypatch.setattr(settings, "PLUGIN_PACKAGE_PATH", str(plugin_root))
    monkeypatch.setattr(settings, "PLUGIN_DATA_PATH", str(data_root))
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    runtime = register_builtin_plugin_routes(app)
    app.state.plugin_runtime_state_storage = InMemoryPluginRuntimeStateStorage()
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_admin
    client = TestClient(app)

    response = client.get("/plugin-assets/asset_plugin/widget.js")
    blocked_escape = client.get("/plugin-assets/asset_plugin/../plugin.yaml")
    runtime.disable_plugin("asset_plugin")
    disabled_response = client.get("/plugin-assets/asset_plugin/widget.js")

    assert response.status_code == 200
    assert response.content == b"export const value = 1;\n"
    assert blocked_escape.status_code == 404
    assert disabled_response.status_code == 503
    runtime_plugin = next(
        item
        for item in client.get("/api/extensions/plugins/").json()["plugins"]
        if item["plugin_id"] == "asset_plugin"
    )
    assert runtime_plugin["package"]["layout"]["has_frontend_dist"] is True
    assert runtime_plugin["package"]["frontend_assets"] is None
    records = runtime.resource_ledger.list(plugin_id="asset_plugin")
    frontend_asset_record = next(
        record for record in records if record.resource_type.value == "plugin_frontend_asset"
    )
    assert frontend_asset_record.metadata["asset_mount"] == "/plugin-assets/asset_plugin/"


def test_plugin_runtime_exposes_frontend_asset_bundle_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    plugin_folder = plugin_root / "installed" / "asset_plugin"
    dist_dir = plugin_folder / "frontend" / "dist"
    dist_dir.mkdir(parents=True)
    (plugin_folder / "plugin.yaml").write_text(
        """
id: asset_plugin
name: Asset Plugin
version: 1.0.0
api_version: v1
enabled_by_default: true
""",
        encoding="utf-8",
    )
    (dist_dir / "widget.js").write_bytes(b"export const value = 1;\n")
    (dist_dir / "plugin-assets.json").write_text(
        json.dumps(
            {
                "plugin_id": "asset_plugin",
                "asset_schema": "lambchat.plugin.frontend-assets.v1",
                "slots": ["file_viewer"],
                "assets": ["widget.js"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "PLUGIN_PACKAGE_PATH", str(plugin_root))
    monkeypatch.setattr(settings, "PLUGIN_DATA_PATH", str(data_root))
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    runtime = register_builtin_plugin_routes(app)
    app.state.plugin_runtime_state_storage = InMemoryPluginRuntimeStateStorage()
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_admin
    client = TestClient(app)

    runtime_plugin = next(
        item
        for item in client.get("/api/extensions/plugins/").json()["plugins"]
        if item["plugin_id"] == "asset_plugin"
    )
    package_export = client.get("/api/extensions/plugins/asset_plugin/package-export")
    records = runtime.resource_ledger.list(plugin_id="asset_plugin")
    frontend_asset_record = next(
        record for record in records if record.resource_type.value == "plugin_frontend_asset"
    )

    assert runtime_plugin["package"]["frontend_assets"] == {
        "plugin_id": "asset_plugin",
        "asset_schema": "lambchat.plugin.frontend-assets.v1",
        "slots": ["file_viewer"],
        "assets": ["widget.js"],
        "phase": "static_asset_mount_placeholder",
    }
    assert package_export.status_code == 200
    assert package_export.json()["package_summary"]["frontend_assets"]["assets"] == ["widget.js"]
    assert frontend_asset_record.metadata["asset_schema"] == "lambchat.plugin.frontend-assets.v1"
    assert frontend_asset_record.metadata["slots"] == "file_viewer"
    assert frontend_asset_record.metadata["asset_count"] == "1"


def test_plugin_runtime_export_import_and_uninstall_controls() -> None:
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    runtime = register_builtin_plugin_routes(app)
    storage = InMemoryPluginRuntimeStateStorage()
    app.state.plugin_runtime_state_storage = storage
    app.state.plugin_settings_service = PluginSettingsService(
        storage=InMemoryPluginSettingsStorage()
    )
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_admin
    client = TestClient(app)

    exported = client.get(
        f"/api/extensions/plugins/{IMAGE_GENERATION_PLUGIN_ID}/export"
    )
    dry_run = client.get(
        f"/api/extensions/plugins/{IMAGE_GENERATION_PLUGIN_ID}/uninstall-dry-run"
    )
    uninstall_without_snapshot = client.post(
        f"/api/extensions/plugins/{IMAGE_GENERATION_PLUGIN_ID}/uninstall",
        json={"snapshot_id": "missing", "confirmed": True},
    )
    uninstall = client.post(
        f"/api/extensions/plugins/{IMAGE_GENERATION_PLUGIN_ID}/uninstall",
        json={
            "snapshot_id": dry_run.json()["snapshot_id"],
            "confirmed": True,
            "reason": "test uninstall",
        },
    )
    imported = client.post(
        "/api/extensions/plugins/import",
        json={"payload": exported.json(), "restore_state": False},
    )

    assert exported.status_code == 200
    export_payload = exported.json()
    assert export_payload["schema_version"] == "lambchat.plugin.export.v1"
    assert export_payload["install_type"] == "preinstalled"
    assert export_payload["uninstallable"] is True
    api_key = next(item for item in export_payload["settings"] if item["key"] == "API_KEY")
    assert api_key["sensitive"] is True
    assert api_key["value"] in {"", "********"}

    assert dry_run.status_code == 200
    assert uninstall_without_snapshot.status_code == 409
    assert uninstall_without_snapshot.json()["detail"]["error"] == (
        "plugin_uninstall_dry_run_invalid"
    )
    assert uninstall.status_code == 200
    assert uninstall.json()["status"] == "uninstalled"
    assert uninstall.json()["package_action"] == "state_only"
    assert uninstall.json()["package_archive_path"] is None
    assert uninstall.json()["plugin_data_retained"] is True
    assert runtime.get_state(IMAGE_GENERATION_PLUGIN_ID).status is (
        PluginRuntimeStatus.UNINSTALLED
    )
    assert storage.audit_records[-1].action == "uninstall"
    assert imported.status_code == 200
    assert imported.json()["plugin_id"] == IMAGE_GENERATION_PLUGIN_ID


def test_plugin_runtime_uninstall_archives_user_installed_package_and_keeps_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    source = tmp_path / "incoming" / "folder_plugin"
    source.mkdir(parents=True)
    (source / "plugin.yaml").write_text(
        """
id: folder_plugin
name: Folder Plugin
version: 1.0.0
api_version: v1
enabled_by_default: false
settings: []
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "PLUGIN_PACKAGE_PATH", str(plugin_root))
    monkeypatch.setattr(settings, "PLUGIN_DATA_PATH", str(data_root))
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    storage = InMemoryPluginRuntimeStateStorage()
    app.state.plugin_runtime_state_storage = storage
    register_builtin_plugin_routes(app)
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_admin
    client = TestClient(app)

    installed = client.post(
        "/api/extensions/plugins/packages/import",
        json={"source_path": str(source), "dry_run": False},
    )
    assert installed.status_code == 200
    assert installed.json()["integrity"]["algorithm"] == "sha256:sorted-file-list-v1"
    assert len(installed.json()["integrity"]["package_sha256"]) == 64
    assert installed.json()["integrity"]["signature_status"] == "unsigned"
    enable_unsigned = client.post("/api/extensions/plugins/folder_plugin/enable")
    assert enable_unsigned.status_code == 409
    assert enable_unsigned.json()["detail"]["error"] == "plugin_package_unsigned"
    assert enable_unsigned.json()["detail"]["package_sha256"] == installed.json()["integrity"]["package_sha256"]
    installed_path = plugin_root / "installed" / "folder_plugin"
    data_path = data_root / "folder_plugin"
    (data_path / "storage" / "user.txt").write_text("keep me\n", encoding="utf-8")

    dry_run = client.get("/api/extensions/plugins/folder_plugin/uninstall-dry-run")
    uninstall = client.post(
        "/api/extensions/plugins/folder_plugin/uninstall",
        json={"snapshot_id": dry_run.json()["snapshot_id"], "confirmed": True},
    )

    assert dry_run.status_code == 200
    assert uninstall.status_code == 200
    payload = uninstall.json()
    assert payload["status"] == "uninstalled"
    assert payload["package_action"] == "archive_package_folder"
    assert payload["package_archive_path"]
    archive_path = Path(payload["package_archive_path"])
    assert archive_path.parent == plugin_root / "archived"
    assert (archive_path / "plugin.yaml").is_file()
    assert not installed_path.exists()
    assert data_path.exists()
    assert (data_path / "storage" / "user.txt").read_text(encoding="utf-8") == "keep me\n"
    assert payload["plugin_data_retained"] is True
    assert payload["plugin_data_dir"] == str(data_path)
    assert len(payload["package_integrity"]["package_sha256"]) == 64
    assert payload["package_integrity"]["signature_status"] == "unsigned"
    assert any("plugin-data is retained" in warning for warning in payload["warnings"])
    listed = client.get("/api/extensions/plugins/").json()["plugins"]
    assert all(item["plugin_id"] != "folder_plugin" for item in listed)

    archived = client.get("/api/extensions/plugins/packages/archived")
    assert archived.status_code == 200
    archived_payload = archived.json()
    assert archived_payload["total"] == 1
    archived_package = archived_payload["archived"][0]
    assert archived_package["plugin_id"] == "folder_plugin"
    assert archived_package["valid"] is True
    assert archived_package["data_dir"] == str(data_path)
    assert archived_package["integrity"]["package_sha256"] == payload["package_integrity"]["package_sha256"]

    restored = client.post(
        f"/api/extensions/plugins/packages/archived/{archived_package['archive_id']}/restore"
    )
    assert restored.status_code == 200
    restored_payload = restored.json()
    assert restored_payload["status"] == "restored"
    assert restored_payload["target_path"] == str(installed_path)
    assert restored_payload["integrity"]["package_sha256"] == payload["package_integrity"]["package_sha256"]
    assert installed_path.exists()
    assert not archive_path.exists()
    assert (data_path / "storage" / "user.txt").read_text(encoding="utf-8") == "keep me\n"
    listed_after_restore = client.get("/api/extensions/plugins/").json()["plugins"]
    restored_plugin = next(item for item in listed_after_restore if item["plugin_id"] == "folder_plugin")
    assert restored_plugin["status"] == "disabled"
    assert storage.audit_records[-1].action == "package_restore"
    enable_restored_unsigned = client.post("/api/extensions/plugins/folder_plugin/enable")
    assert enable_restored_unsigned.status_code == 409
    assert enable_restored_unsigned.json()["detail"]["error"] == "plugin_package_unsigned"


def test_plugin_runtime_package_review_allows_current_unsigned_hash_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    source = tmp_path / "incoming" / "review_plugin"
    source.mkdir(parents=True)
    (source / "plugin.yaml").write_text(
        """
id: review_plugin
name: Review Plugin
version: 1.0.0
api_version: v1
enabled_by_default: false
settings: []
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "PLUGIN_PACKAGE_PATH", str(plugin_root))
    monkeypatch.setattr(settings, "PLUGIN_DATA_PATH", str(data_root))
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    storage = InMemoryPluginRuntimeStateStorage()
    app.state.plugin_runtime_state_storage = storage
    register_builtin_plugin_routes(app)
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_admin
    client = TestClient(app)

    installed = client.post(
        "/api/extensions/plugins/packages/import",
        json={"source_path": str(source), "dry_run": False},
    )
    assert installed.status_code == 200
    original_hash = installed.json()["integrity"]["package_sha256"]

    review_before = client.get("/api/extensions/plugins/review_plugin/package-review")
    assert review_before.status_code == 200
    assert review_before.json()["package_sha256"] == original_hash
    assert review_before.json()["active_for_current_package"] is False

    enable_before_review = client.post("/api/extensions/plugins/review_plugin/enable")
    assert enable_before_review.status_code == 409
    assert enable_before_review.json()["detail"]["error"] == "plugin_package_unsigned"
    assert enable_before_review.json()["detail"]["package_sha256"] == original_hash

    reviewed = client.post(
        "/api/extensions/plugins/review_plugin/package-review",
        json={"reason": "local test review"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["package_sha256"] == original_hash
    assert reviewed.json()["active_for_current_package"] is True
    assert reviewed.json()["reviewer_username"] == "admin"
    assert storage.audit_records[-1].action == "package_review"

    enable_after_review = client.post("/api/extensions/plugins/review_plugin/enable")
    assert enable_after_review.status_code == 200
    assert enable_after_review.json()["status"] == "enabled"

    installed_path = plugin_root / "installed" / "review_plugin"
    (installed_path / "README.md").write_text("changed package contents\n", encoding="utf-8")
    disable_after_change = client.post("/api/extensions/plugins/review_plugin/disable")
    assert disable_after_change.status_code == 200
    review_after_change = client.get("/api/extensions/plugins/review_plugin/package-review")
    assert review_after_change.status_code == 200
    changed_hash = review_after_change.json()["package_sha256"]
    assert changed_hash != original_hash
    assert review_after_change.json()["active_for_current_package"] is False
    enable_after_change = client.post("/api/extensions/plugins/review_plugin/enable")
    assert enable_after_change.status_code == 409
    assert enable_after_change.json()["detail"]["error"] == "plugin_package_unsigned"
    assert enable_after_change.json()["detail"]["package_sha256"] == changed_hash


def test_plugin_package_import_warns_about_missing_dependencies(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    source = tmp_path / "incoming" / "dependency_plugin"
    source.mkdir(parents=True)
    (source / "plugin.yaml").write_text(
        """
id: dependency_plugin
name: Dependency Plugin
version: 1.0.0
api_version: v1
enabled_by_default: false
depends_on:
  - missing_plugin
settings: []
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "PLUGIN_PACKAGE_PATH", str(plugin_root))
    monkeypatch.setattr(settings, "PLUGIN_DATA_PATH", str(data_root))
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    app.state.plugin_runtime_state_storage = InMemoryPluginRuntimeStateStorage()
    register_builtin_plugin_routes(app)
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_admin
    client = TestClient(app)

    dry_run = client.post(
        "/api/extensions/plugins/packages/import",
        json={"source_path": str(source), "dry_run": True},
    )
    installed = client.post(
        "/api/extensions/plugins/packages/import",
        json={"source_path": str(source), "dry_run": False},
    )

    assert dry_run.status_code == 200
    assert any("missing_plugin" in warning for warning in dry_run.json()["warnings"])
    assert installed.status_code == 200
    assert any("missing_plugin" in warning for warning in installed.json()["warnings"])
    listed = client.get("/api/extensions/plugins/").json()["plugins"]
    plugin = next(item for item in listed if item["plugin_id"] == "dependency_plugin")
    assert plugin["depends_on"] == ["missing_plugin"]
    assert any(issue["code"] == "missing_dependency" for issue in plugin["issues"])


def test_plugin_runtime_rejects_uninstall_for_system_preset_plugins() -> None:
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    register_builtin_plugin_routes(app)
    app.state.plugin_runtime_state_storage = InMemoryPluginRuntimeStateStorage()
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_admin
    client = TestClient(app)

    dry_run = client.get(f"/api/extensions/plugins/{USAGE_REPORTS_PLUGIN_ID}/uninstall-dry-run")
    response = client.post(
        f"/api/extensions/plugins/{USAGE_REPORTS_PLUGIN_ID}/uninstall",
        json={"snapshot_id": dry_run.json()["snapshot_id"], "confirmed": True},
    )

    assert dry_run.status_code == 200
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "plugin_uninstall_protected"


def test_plugin_runtime_routes_return_404_for_unknown_plugin() -> None:
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    register_builtin_plugin_routes(app)
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_reader

    response = TestClient(app).get("/api/extensions/plugins/missing")

    assert response.status_code == 404


def test_plugin_runtime_control_routes_disable_enable_feedback_guard() -> None:
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    runtime = register_builtin_plugin_routes(app)
    storage = InMemoryPluginRuntimeStateStorage()
    app.state.plugin_runtime_state_storage = storage
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_admin
    client = TestClient(app)

    disabled = client.post(f"/api/extensions/plugins/{FEEDBACK_PLUGIN_ID}/disable")
    blocked_feedback = client.get("/api/feedback/")

    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    assert disabled.json()["executable"] is False
    assert disabled.json()["state_source"] == "stored_override"
    assert disabled.json()["state_updated_by"] == "admin-1"
    assert len(storage.audit_records) == 1
    assert storage.audit_records[0].action == "disable"
    assert runtime.get_state(FEEDBACK_PLUGIN_ID).status is PluginRuntimeStatus.DISABLED
    assert blocked_feedback.status_code == 503
    assert blocked_feedback.json()["detail"]["error"] == "plugin_unavailable"

    enabled = client.post(f"/api/extensions/plugins/{FEEDBACK_PLUGIN_ID}/enable")

    assert enabled.status_code == 200
    assert enabled.json()["status"] == "enabled"
    assert enabled.json()["executable"] is True
    assert len(storage.audit_records) == 2
    assert storage.audit_records[1].action == "enable"
    assert runtime.get_state(FEEDBACK_PLUGIN_ID).status is PluginRuntimeStatus.ENABLED


def test_agent_team_plugin_route_is_guarded_by_runtime_state() -> None:
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    runtime = register_builtin_plugin_routes(app)
    app.state.plugin_runtime_state_storage = InMemoryPluginRuntimeStateStorage()
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_admin
    client = TestClient(app)

    disabled = client.post(f"/api/extensions/plugins/{AGENT_TEAM_PLUGIN_ID}/disable")
    blocked_teams = client.get("/api/teams/")

    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    assert runtime.get_state(AGENT_TEAM_PLUGIN_ID).status is PluginRuntimeStatus.DISABLED
    assert blocked_teams.status_code == 503
    assert blocked_teams.json()["detail"]["error"] == "plugin_unavailable"


def test_plugin_runtime_control_routes_apply_feishu_connector_runtime_side_effects(
    monkeypatch,
) -> None:
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    runtime = register_builtin_plugin_routes(app)
    app.state.plugin_runtime_state_storage = InMemoryPluginRuntimeStateStorage()
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_admin
    calls: list[str] = []

    async def fake_stop_feishu_channels() -> None:
        calls.append("stop")

    async def fake_setup_feishu_handler(*, default_agent: str, show_tools: bool) -> None:
        calls.append(f"start:{default_agent}:{show_tools}")

    monkeypatch.setattr(
        "src.infra.channel.feishu.stop_feishu_channels",
        fake_stop_feishu_channels,
    )
    monkeypatch.setattr(
        "src.infra.channel.feishu.handler.setup_feishu_handler",
        fake_setup_feishu_handler,
    )
    client = TestClient(app)

    disabled = client.post(f"/api/extensions/plugins/{FEISHU_CONNECTOR_PLUGIN_ID}/disable")
    enabled = client.post(f"/api/extensions/plugins/{FEISHU_CONNECTOR_PLUGIN_ID}/enable")

    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    assert disabled.json()["runtime_side_effect"] == {
        "action": "stop_feishu_connector",
        "status": "succeeded",
        "message": "Feishu connector stop was requested successfully.",
    }
    assert enabled.status_code == 200
    assert enabled.json()["status"] == "enabled"
    assert enabled.json()["runtime_side_effect"] == {
        "action": "start_feishu_connector",
        "status": "succeeded",
        "message": "Feishu connector startup was requested successfully.",
    }
    assert calls == ["stop", f"start:{settings.DEFAULT_AGENT}:True"]
    assert runtime.get_state(FEISHU_CONNECTOR_PLUGIN_ID).status is PluginRuntimeStatus.ENABLED


def test_plugin_runtime_control_routes_expose_feishu_side_effect_failures(
    monkeypatch,
) -> None:
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    runtime = register_builtin_plugin_routes(app)
    app.state.plugin_runtime_state_storage = InMemoryPluginRuntimeStateStorage()
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_admin

    async def fake_stop_feishu_channels() -> None:
        raise RuntimeError("stop failed for test")

    monkeypatch.setattr(
        "src.infra.channel.feishu.stop_feishu_channels",
        fake_stop_feishu_channels,
    )
    client = TestClient(app)

    response = client.post(
        f"/api/extensions/plugins/{FEISHU_CONNECTOR_PLUGIN_ID}/disable"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "disabled"
    assert payload["runtime_side_effect"] == {
        "action": "stop_feishu_connector",
        "status": "failed",
        "message": "stop failed for test",
    }
    assert runtime.get_state(FEISHU_CONNECTOR_PLUGIN_ID).status is PluginRuntimeStatus.DISABLED


def test_plugin_runtime_audit_route_returns_state_changes() -> None:
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    register_builtin_plugin_routes(app)
    app.state.plugin_runtime_state_storage = InMemoryPluginRuntimeStateStorage()
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_admin
    client = TestClient(app)

    client.post(f"/api/extensions/plugins/{FEEDBACK_PLUGIN_ID}/disable")
    client.post(f"/api/extensions/plugins/{FEEDBACK_PLUGIN_ID}/enable")
    response = client.get(f"/api/extensions/plugins/{FEEDBACK_PLUGIN_ID}/audit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["plugin_id"] == FEEDBACK_PLUGIN_ID
    assert payload["total"] == 2
    assert [item["action"] for item in payload["audit"]] == ["enable", "disable"]
    assert payload["audit"][0]["actor_user_id"] == "admin-1"


def test_plugin_runtime_control_routes_require_admin_permission() -> None:
    app = FastAPI()
    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration(
                "plugin_runtime",
                "src.api.routes.plugin_runtime",
                prefix="/api/extensions/plugins",
            ),
        ),
    )
    register_builtin_plugin_routes(app)
    app.dependency_overrides[api_deps.get_current_user_required] = _plugin_runtime_reader

    response = TestClient(app).post(
        f"/api/extensions/plugins/{FEEDBACK_PLUGIN_ID}/disable"
    )

    assert response.status_code == 403


def test_register_plugin_routes_includes_enabled_routes_with_guard():
    router = APIRouter()

    @router.get("/ping")
    async def ping():
        return {"ok": True}

    module = ModuleType("tests.fake_plugin_route_module")
    module.router = router
    sys.modules[module.__name__] = module

    runtime = PluginRuntime(
        [
            PluginManifest(
                id="feedback",
                name="Feedback",
                version="1.0.0",
                api_version="v1",
                permissions=["feedback:read"],
                routers=[
                    {
                        "name": "feedback-api",
                        "prefix": "/api/plugins/feedback",
                        "module": module.__name__,
                    }
                ],
            )
        ]
    )
    app = FastAPI()

    register_plugin_routes(app, runtime)

    response = TestClient(app).get("/api/plugins/feedback/ping")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_register_plugin_routes_skips_disabled_plugins() -> None:
    router = APIRouter()

    @router.get("/ping")
    async def ping():
        return {"ok": True}

    module = ModuleType("tests.fake_disabled_plugin_route_module")
    module.router = router
    sys.modules[module.__name__] = module

    runtime = PluginRuntime(
        [
            PluginManifest(
                id="feedback",
                name="Feedback",
                version="1.0.0",
                api_version="v1",
                permissions=["feedback:read"],
                enabled_by_default=False,
                routers=[
                    {
                        "name": "feedback-api",
                        "prefix": "/api/plugins/feedback",
                        "module": module.__name__,
                    }
                ],
            )
        ]
    )
    app = FastAPI()

    register_plugin_routes(app, runtime, registrations=runtime.routes(enabled_only=False))

    assert runtime.get_state("feedback").status is PluginRuntimeStatus.DISABLED
    assert runtime.get_state("feedback").issues == []
    response = TestClient(app).get("/api/plugins/feedback/ping")
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "plugin_unavailable"


def test_register_plugin_routes_records_import_errors_without_blocking_core_routes() -> None:
    core_router = APIRouter()

    @core_router.get("/health")
    async def health():
        return {"ok": True}

    core_module = ModuleType("tests.fake_core_route_module")
    core_module.router = core_router
    sys.modules[core_module.__name__] = core_module

    runtime = PluginRuntime(
        [
            PluginManifest(
                id="feedback",
                name="Feedback",
                version="1.0.0",
                api_version="v1",
                permissions=["feedback:read"],
                routers=[
                    {
                        "name": "feedback-api",
                        "prefix": "/api/plugins/feedback",
                        "module": "tests.missing_plugin_route_module",
                    }
                ],
            )
        ]
    )
    app = FastAPI()

    register_core_routes(
        app,
        registrations=(
            CoreRouteRegistration("health", core_module.__name__, prefix="/api"),
        ),
    )
    register_plugin_routes(app, runtime)

    assert runtime.get_state("feedback").status is PluginRuntimeStatus.ERROR
    assert runtime.get_state("feedback").issues[-1].code == "route_registration_failed"
    assert TestClient(app).get("/api/health").status_code == 200

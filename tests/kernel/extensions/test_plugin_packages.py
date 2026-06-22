import json
import os
from pathlib import Path
from zipfile import ZipFile

import pytest

import src.infra.extensions.plugin_package_import as plugin_package_import
from src.infra.extensions.plugin_data import PluginDataService
from src.infra.extensions.plugin_package_import import (
    PluginPackageImportService,
)
from src.infra.extensions.plugin_package_lifecycle import PluginPackageLifecycleService
from src.kernel.extensions import BUILTIN_PLUGIN_MANIFESTS
from src.kernel.extensions.host_slots import (
    BACKEND_PLUGIN_MANIFEST_KEYS,
    CONTROLLED_FRONTEND_REFERENCES,
    FRONTEND_MANIFEST_CONTRIBUTION_KEYS,
    STRUCTURED_FRONTEND_MANIFEST_KEYS,
    STRUCTURED_OR_LEGACY_STRING_FRONTEND_MANIFEST_KEYS,
)
from src.kernel.extensions.packages import PluginPackageScanner


def _write_plugin(root: Path, source: str, plugin_id: str, body: str) -> Path:
    folder = root / source / plugin_id
    folder.mkdir(parents=True)
    (folder / "plugin.yaml").write_text(body, encoding="utf-8")
    return folder


def test_plugin_package_scanner_compiles_folder_manifest(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    _write_plugin(
        plugin_root,
        "installed",
        "demo_plugin",
        """
id: demo_plugin
name: Demo Plugin
version: 1.0.0
api_version: v1
permissions:
  - demo_plugin:read
settings:
  - key: MODEL
    type: string
    default: demo
frontend:
  nav_items:
    - demo_plugin:nav
backend:
  tools:
    - name: demo_plugin_tool
      module: plugins.demo.tool
      legacy_ids:
        - demo_plugin.tool
""",
    )

    scan = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan()

    assert scan.errors == ()
    assert len(scan.descriptors) == 1
    manifest = scan.manifests[0]
    assert manifest.id == "demo_plugin"
    assert manifest.install_type.value == "user_installed"
    assert manifest.package_source_type == "installed"
    assert manifest.package_manifest_authority == "folder_package"
    assert manifest.package_static_fallback_used is False
    assert manifest.package_static_fallback_fields == []
    assert manifest.package_data_dir == str(data_root.resolve() / "demo_plugin")
    assert manifest.settings[0].key == "MODEL"


def test_plugin_package_scanner_reports_folder_layout(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "demo_plugin",
        """
id: demo_plugin
name: Demo Plugin
version: 1.0.0
api_version: v1
""",
    )
    (folder / "backend").mkdir()
    (folder / "backend" / "tools.py").write_text("", encoding="utf-8")
    (folder / "backend" / "plugin.json").write_text(
        '{"schema":"lambchat.plugin.backend.v1","plugin_id":"demo_plugin","backend":{"tools":[{"name":"demo_plugin_tool","module":"plugins.demo.tool","legacy_ids":["demo_plugin.tool"]}]}}',
        encoding="utf-8",
    )
    (folder / "frontend" / "dist").mkdir(parents=True)
    (folder / "frontend" / "plugin.json").write_text(
        '{"schema":"lambchat.plugin.frontend.v1","plugin_id":"demo_plugin","frontend":{"nav_items":["demo_plugin:nav"]}}',
        encoding="utf-8",
    )
    (folder / "config").mkdir()
    (folder / "config" / "schema.json").write_text("[]", encoding="utf-8")
    (folder / "plugin-data-template" / "state").mkdir(parents=True)
    (folder / "plugin-data-template" / "state" / "audit.jsonl").write_text("", encoding="utf-8")
    (folder / "resources").mkdir()
    (folder / "resources" / "resources.yaml").write_text("[]", encoding="utf-8")
    (folder / "README.md").write_text("Demo", encoding="utf-8")

    descriptor = (
        PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan().descriptors[0]
    )

    assert descriptor.layout.has_backend is True
    assert descriptor.layout.has_frontend is True
    assert descriptor.layout.has_frontend_dist is True
    assert descriptor.layout.has_config_schema is True
    assert descriptor.layout.has_resources is True
    assert descriptor.layout.has_data_template is True
    assert descriptor.layout.data_template == "plugin-data-template"
    assert descriptor.layout.has_readme is True
    assert descriptor.layout.backend_files == ("plugin.json", "tools.py")
    assert descriptor.layout.frontend_files == ("dist/", "plugin.json")
    assert descriptor.manifest is not None
    assert descriptor.manifest.package_layout["has_backend"] is True
    assert descriptor.manifest.package_layout["has_frontend_dist"] is True
    assert descriptor.manifest.package_layout["data_template"] == "plugin-data-template"


def test_plugin_package_scanner_compiles_backend_plugin_file(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "backend_plugin",
        """
id: backend_plugin
name: Backend Plugin
version: 1.0.0
api_version: v1
""",
    )
    (folder / "backend").mkdir()
    (folder / "backend" / "plugin.json").write_text(
        json.dumps(
            {
                "schema": "lambchat.plugin.backend.v1",
                "plugin_id": "backend_plugin",
                "backend": {
                    "routers": [
                        {
                            "name": "backend_plugin-api",
                            "prefix": "/api/backend-plugin",
                            "module": "plugins.backend_plugin.routes",
                            "required_permissions": ["backend_plugin:read"],
                            "tags": ["Backend Plugin"],
                        }
                    ],
                    "agents": [
                        {
                            "id": "demo_agent",
                            "module": "plugins.backend_plugin.agent.DemoAgent",
                            "name": "Demo Agent",
                            "required_permissions": ["backend_plugin:read"],
                        }
                    ],
                    "tools": [
                        {
                            "name": "backend_plugin_tool",
                            "module": "plugins.backend_plugin.tools",
                            "required_permissions": ["backend_plugin:read"],
                            "legacy_ids": ["backend_tool", "backend_plugin.tool"],
                        }
                    ],
                    "lifespan_hooks": [
                        {
                            "name": "backend_plugin:shutdown",
                            "module": "plugins.backend_plugin.lifecycle:shutdown",
                            "phase": "shutdown",
                            "order": 50,
                        }
                    ],
                    "runtime_effects": [
                        {
                            "action": "disable",
                            "effect": "stop_feishu_connector",
                        }
                    ],
                    "scheduler_jobs": ["backend_plugin:job"],
                    "event_listeners": ["backend_plugin:event-listener"],
                    "migrations": ["backend_plugin:migration-001"],
                },
            }
        ),
        encoding="utf-8",
    )

    descriptor = (
        PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan().descriptors[0]
    )

    assert descriptor.errors == ()
    manifest = descriptor.manifest
    assert manifest is not None
    assert manifest.routers[0].name == "backend_plugin-api"
    assert manifest.routers[0].prefix == "/api/backend-plugin"
    assert manifest.agents[0].id == "demo_agent"
    assert manifest.agents[0].module == "plugins.backend_plugin.agent.DemoAgent"
    assert manifest.tools[0].name == "backend_plugin_tool"
    assert manifest.tools[0].legacy_ids == ["backend_tool", "backend_plugin.tool"]
    assert manifest.lifespan_hooks[0].name == "backend_plugin:shutdown"
    assert manifest.runtime_effects[0].action == "disable"
    assert manifest.runtime_effects[0].effect == "stop_feishu_connector"
    assert manifest.scheduler_jobs == ["backend_plugin:job"]
    assert manifest.event_listeners == ["backend_plugin:event-listener"]
    assert manifest.migrations == ["backend_plugin:migration-001"]


def test_plugin_package_scanner_accepts_backend_routes_alias(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "routes_plugin",
        """
id: routes_plugin
name: Routes Plugin
version: 1.0.0
api_version: v1
backend:
  routes:
    - name: routes_plugin-yaml-api
      prefix: /api/routes-plugin-yaml
      module: plugins.routes_plugin.yaml_routes
""",
    )
    (folder / "backend").mkdir()
    (folder / "backend" / "plugin.json").write_text(
        json.dumps(
            {
                "schema": "lambchat.plugin.backend.v1",
                "plugin_id": "routes_plugin",
                "backend": {
                    "routes": [
                        {
                            "name": "routes_plugin-json-api",
                            "prefix": "/api/routes-plugin-json",
                            "module": "plugins.routes_plugin.json_routes",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    descriptor = (
        PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan().descriptors[0]
    )

    assert descriptor.errors == ()
    manifest = descriptor.manifest
    assert manifest is not None
    assert [(route.name, route.prefix, route.module) for route in manifest.routers] == [
        (
            "routes_plugin-yaml-api",
            "/api/routes-plugin-yaml",
            "plugins.routes_plugin.yaml_routes",
        ),
        (
            "routes_plugin-json-api",
            "/api/routes-plugin-json",
            "plugins.routes_plugin.json_routes",
        ),
    ]


def test_plugin_package_scanner_rejects_conflicting_backend_routes_aliases(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "routes_plugin",
        """
id: routes_plugin
name: Routes Plugin
version: 1.0.0
api_version: v1
""",
    )
    (folder / "backend").mkdir()
    (folder / "backend" / "plugin.json").write_text(
        json.dumps(
            {
                "schema": "lambchat.plugin.backend.v1",
                "plugin_id": "routes_plugin",
                "backend": {
                    "routes": [
                        {
                            "name": "routes_plugin-api",
                            "prefix": "/api/routes-plugin",
                            "module": "plugins.routes_plugin.routes",
                        }
                    ],
                    "routers": [
                        {
                            "name": "routes_plugin-other-api",
                            "prefix": "/api/routes-plugin-other",
                            "module": "plugins.routes_plugin.other_routes",
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    scan = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan()

    assert scan.descriptors[0].manifest is None
    assert "routes and routers cannot both declare different routes" in scan.errors[0]


def test_plugin_package_scanner_rejects_backend_plugin_file_for_wrong_plugin(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "backend_plugin",
        """
id: backend_plugin
name: Backend Plugin
version: 1.0.0
api_version: v1
""",
    )
    (folder / "backend").mkdir()
    (folder / "backend" / "plugin.json").write_text(
        json.dumps(
            {
                "schema": "lambchat.plugin.backend.v1",
                "plugin_id": "other_plugin",
                "backend": {"tools": []},
            }
        ),
        encoding="utf-8",
    )

    scan = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan()

    assert scan.descriptors[0].manifest is None
    assert "backend/plugin.json plugin_id must match" in scan.errors[0]


def test_plugin_package_scanner_rejects_unknown_backend_plugin_file_key(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "backend_plugin",
        """
id: backend_plugin
name: Backend Plugin
version: 1.0.0
api_version: v1
""",
    )
    (folder / "backend").mkdir()
    (folder / "backend" / "plugin.json").write_text(
        json.dumps(
            {
                "schema": "lambchat.plugin.backend.v1",
                "plugin_id": "backend_plugin",
                "backend": {"arbitrary_code": []},
            }
        ),
        encoding="utf-8",
    )

    scan = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan()

    assert scan.descriptors[0].manifest is None
    assert "unknown contribution key" in scan.errors[0]


def test_plugin_package_scanner_compiles_frontend_plugin_file(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "frontend_plugin",
        """
id: frontend_plugin
name: Frontend Plugin
version: 1.0.0
api_version: v1
settings:
  - key: DEFAULT_ITEM_ID
    type: string
    scope: project
  - key: SELECTED_ITEM_ID
    type: string
    scope: session
  - key: SELECTED_CHANNEL_ITEM_ID
    type: string
    scope: channel
  - key: SELECTED_TASK_ITEM_ID
    type: string
    scope: scheduled_task
""",
    )
    (folder / "frontend").mkdir()
    (folder / "frontend" / "plugin.json").write_text(
        json.dumps(
            {
                "schema": "lambchat.plugin.frontend.v1",
                "plugin_id": "frontend_plugin",
                "frontend": {
                    "routes": ["frontend_plugin:route"],
                    "panels": ["frontend_plugin:panel"],
                    "nav_items": ["frontend_plugin:nav"],
                    "app_tabs": [
                        {
                            "id": "frontend_plugin:tab",
                            "tab": "feedback",
                            "path": "/frontend-plugin",
                            "label": "frontendPlugin.nav",
                            "panel": "frontend_plugin:panel",
                            "insert_after": "settings",
                            "permissions": ["frontend_plugin:read"],
                        }
                    ],
                    "app_panels": [
                        {
                            "id": "frontend_plugin:panel",
                            "tab": "feedback",
                            "renderer": "frontend_plugin.Panel",
                        }
                    ],
                    "sidebar_items": [
                        {
                            "id": "frontend_plugin:sidebar",
                            "path": "/frontend-plugin",
                            "label": "frontendPlugin.nav",
                            "icon": "Plug",
                        }
                    ],
                    "user_menu_items": [
                        {
                            "id": "frontend_plugin:user-menu",
                            "path": "/frontend-plugin",
                            "label": "frontendPlugin.nav",
                            "icon": "Plug",
                            "group": "system",
                        }
                    ],
                    "message_actions": [
                        {
                            "id": "frontend_plugin:message-action",
                            "target": "assistant_message",
                            "renderer": "frontend_plugin.MessageAction",
                            "order": 50,
                        }
                    ],
                    "chat_input_options": [
                        {
                            "id": "frontend_plugin:open-panel",
                            "slot": "enhance",
                            "label": "frontendPlugin.open",
                            "icon": "Plug",
                            "panel": "frontend_plugin:panel-picker",
                            "selected_renderer": "frontend_plugin.SelectedChip",
                            "suppresses_core_persona_selector": True,
                            "shortcut": "mod+k",
                            "option_binding": {
                                "plugin_id": "frontend_plugin",
                                "key": "SELECTED_ITEM_ID",
                                "scope": "session",
                            },
                            "visible_when": {"agent_id": "team"},
                        }
                    ],
                    "chat_input_panels": [
                        {
                            "id": "frontend_plugin:panel-picker",
                            "renderer": "frontend_plugin.PanelPicker",
                            "create_path": "/frontend-plugin/new",
                            "manage_path": "/frontend-plugin/manage",
                            "option_binding": {
                                "plugin_id": "frontend_plugin",
                                "key": "SELECTED_ITEM_ID",
                                "scope": "session",
                            },
                        }
                    ],
                    "mention_providers": [
                        {
                            "id": "frontend_plugin:mentions",
                            "trigger": "@",
                            "mode": "frontend",
                            "provider": "frontend_plugin.search",
                        }
                    ],
                    "welcome_surfaces": [
                        {
                            "id": "frontend_plugin:welcome",
                            "agent_id": "team",
                            "renderer": "frontend_plugin.WelcomeSurface",
                            "order": 40,
                            "visible_when": {"agent_id": "team"},
                        }
                    ],
                    "agent_categories": [
                        {
                            "id": "frontend_plugin:agents",
                            "label": "frontendPlugin.agents",
                            "description": "Frontend plugin agent category",
                            "icon": "Plug",
                            "order": 30,
                        }
                    ],
                    "project_options": [
                        {
                            "key": "DEFAULT_ITEM_ID",
                            "type": "string",
                            "label": "frontendPlugin.defaultItem",
                            "renderer": "frontend_plugin.DefaultItemSelect",
                        }
                    ],
                    "session_options": [
                        {
                            "key": "SELECTED_ITEM_ID",
                            "type": "string",
                            "label": "frontendPlugin.selectedItem",
                            "visible_when": {"agent_id": "team"},
                        }
                    ],
                    "channel_options": [
                        {
                            "key": "SELECTED_CHANNEL_ITEM_ID",
                            "type": "string",
                            "label": "frontendPlugin.selectedChannelItem",
                            "visible_when": {"route": "/channels/feishu"},
                        }
                    ],
                    "scheduled_task_options": [
                        {
                            "key": "SELECTED_TASK_ITEM_ID",
                            "type": "string",
                            "label": "frontendPlugin.selectedTaskItem",
                            "visible_when": {"agent_id": "team"},
                        }
                    ],
                    "i18n_namespaces": ["frontend_plugin:i18n"],
                    "required_permissions": ["frontend_plugin:read"],
                },
            }
        ),
        encoding="utf-8",
    )

    descriptor = (
        PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan().descriptors[0]
    )

    assert descriptor.errors == ()
    assert descriptor.manifest is not None
    assert descriptor.manifest.frontend.routes == ["frontend_plugin:route"]
    assert descriptor.manifest.frontend.panels == ["frontend_plugin:panel"]
    assert descriptor.manifest.frontend.nav_items == ["frontend_plugin:nav"]
    assert descriptor.manifest.frontend.app_tabs[0].path == "/frontend-plugin"
    assert descriptor.manifest.frontend.app_tabs[0].insert_after == "settings"
    assert descriptor.manifest.frontend.app_panels[0].renderer == "frontend_plugin.Panel"
    assert descriptor.manifest.frontend.sidebar_items[0].label == "frontendPlugin.nav"
    assert descriptor.manifest.frontend.user_menu_items[0].group == "system"
    assert [item.id for item in descriptor.manifest.frontend.message_actions] == [
        "frontend_plugin:message-action"
    ]
    assert (
        descriptor.manifest.frontend.message_actions[0].renderer == "frontend_plugin.MessageAction"
    )
    assert descriptor.manifest.frontend.chat_input_options[0].id == "frontend_plugin:open-panel"
    assert (
        descriptor.manifest.frontend.chat_input_options[0].selected_renderer
        == "frontend_plugin.SelectedChip"
    )
    assert (
        descriptor.manifest.frontend.chat_input_options[0].suppresses_core_persona_selector is True
    )
    assert descriptor.manifest.frontend.chat_input_options[0].shortcut == "mod+k"
    assert descriptor.manifest.frontend.chat_input_options[0].option_binding is not None
    assert (
        descriptor.manifest.frontend.chat_input_options[0].option_binding.plugin_id
        == "frontend_plugin"
    )
    assert (
        descriptor.manifest.frontend.chat_input_options[0].option_binding.key == "SELECTED_ITEM_ID"
    )
    assert descriptor.manifest.frontend.chat_input_options[0].option_binding.scope == "session"
    assert descriptor.manifest.frontend.chat_input_options[0].visible_when is not None
    assert descriptor.manifest.frontend.chat_input_options[0].visible_when.agent_id == "team"
    assert (
        descriptor.manifest.frontend.chat_input_panels[0].renderer == "frontend_plugin.PanelPicker"
    )
    assert descriptor.manifest.frontend.chat_input_panels[0].create_path == "/frontend-plugin/new"
    assert (
        descriptor.manifest.frontend.chat_input_panels[0].manage_path == "/frontend-plugin/manage"
    )
    assert descriptor.manifest.frontend.chat_input_panels[0].option_binding is not None
    assert (
        descriptor.manifest.frontend.chat_input_panels[0].option_binding.plugin_id
        == "frontend_plugin"
    )
    assert (
        descriptor.manifest.frontend.chat_input_panels[0].option_binding.key == "SELECTED_ITEM_ID"
    )
    assert descriptor.manifest.frontend.chat_input_panels[0].option_binding.scope == "session"
    assert descriptor.manifest.frontend.mention_providers[0].provider == "frontend_plugin.search"
    assert (
        descriptor.manifest.frontend.welcome_surfaces[0].renderer
        == "frontend_plugin.WelcomeSurface"
    )
    assert descriptor.manifest.frontend.welcome_surfaces[0].visible_when is not None
    assert descriptor.manifest.frontend.welcome_surfaces[0].visible_when.agent_id == "team"
    assert descriptor.manifest.frontend.agent_categories[0].id == "frontend_plugin:agents"
    assert descriptor.manifest.frontend.agent_categories[0].label == "frontendPlugin.agents"
    assert descriptor.manifest.frontend.project_options[0].key == "DEFAULT_ITEM_ID"
    assert (
        descriptor.manifest.frontend.project_options[0].renderer
        == "frontend_plugin.DefaultItemSelect"
    )
    assert descriptor.manifest.frontend.session_options[0].visible_when is not None
    assert descriptor.manifest.frontend.session_options[0].visible_when.agent_id == "team"
    assert descriptor.manifest.frontend.channel_options[0].key == "SELECTED_CHANNEL_ITEM_ID"
    assert descriptor.manifest.frontend.channel_options[0].visible_when is not None
    assert descriptor.manifest.frontend.channel_options[0].visible_when.route == "/channels/feishu"
    assert descriptor.manifest.frontend.scheduled_task_options[0].key == "SELECTED_TASK_ITEM_ID"
    assert descriptor.manifest.frontend.scheduled_task_options[0].visible_when is not None
    assert descriptor.manifest.frontend.scheduled_task_options[0].visible_when.agent_id == "team"
    assert descriptor.manifest.frontend.i18n_namespaces == ["frontend_plugin:i18n"]
    assert descriptor.manifest.frontend.required_permissions == ["frontend_plugin:read"]


def test_plugin_package_scanner_rejects_frontend_plugin_file_for_wrong_plugin(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "frontend_plugin",
        """
id: frontend_plugin
name: Frontend Plugin
version: 1.0.0
api_version: v1
""",
    )
    (folder / "frontend").mkdir()
    (folder / "frontend" / "plugin.json").write_text(
        json.dumps(
            {
                "schema": "lambchat.plugin.frontend.v1",
                "plugin_id": "other_plugin",
                "frontend": {"nav_items": ["frontend_plugin:nav"]},
            }
        ),
        encoding="utf-8",
    )

    scan = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan()

    assert scan.descriptors[0].manifest is None
    assert "frontend/plugin.json plugin_id must match" in scan.errors[0]


def test_plugin_package_scanner_rejects_unknown_frontend_plugin_file_key(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "frontend_plugin",
        """
id: frontend_plugin
name: Frontend Plugin
version: 1.0.0
api_version: v1
""",
    )
    (folder / "frontend").mkdir()
    (folder / "frontend" / "plugin.json").write_text(
        json.dumps(
            {
                "schema": "lambchat.plugin.frontend.v1",
                "plugin_id": "frontend_plugin",
                "frontend": {"unknown_surface": ["frontend_plugin:x"]},
            }
        ),
        encoding="utf-8",
    )

    scan = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan()

    assert scan.descriptors[0].manifest is None
    assert "unknown contribution key" in scan.errors[0]


def test_frontend_plugin_file_allowed_keys_are_derived_from_host_slots() -> None:
    assert {
        "app_tabs",
        "app_panels",
        "sidebar_items",
        "user_menu_items",
        "message_actions",
        "chat_input_options",
        "chat_input_panels",
        "mention_providers",
        "welcome_surfaces",
        "assistant_identity_resolvers",
        "agent_categories",
        "project_options",
        "session_options",
        "channel_options",
        "scheduled_task_options",
        "tool_renderers",
        "file_viewers",
        "skill_importers",
        "channel_connectors",
        "routes",
        "panels",
        "nav_items",
        "settings_sections",
        "i18n_namespaces",
        "required_permissions",
    } <= FRONTEND_MANIFEST_CONTRIBUTION_KEYS
    assert STRUCTURED_FRONTEND_MANIFEST_KEYS < FRONTEND_MANIFEST_CONTRIBUTION_KEYS
    assert STRUCTURED_OR_LEGACY_STRING_FRONTEND_MANIFEST_KEYS < FRONTEND_MANIFEST_CONTRIBUTION_KEYS


def test_backend_plugin_file_allowed_keys_are_derived_from_host_slots() -> None:
    assert {
        "routes",
        "routers",
        "agents",
        "tools",
        "lifespan_hooks",
        "runtime_effects",
        "scheduler_jobs",
        "event_listeners",
        "migrations",
    } == BACKEND_PLUGIN_MANIFEST_KEYS


def test_controlled_frontend_references_include_builtin_plugin_renderers() -> None:
    assert CONTROLLED_FRONTEND_REFERENCES["app_panels.renderer"] >= {
        "agent_team.TeamBuilderPanel",
        "feedback.FeedbackPanel",
        "usage_reports.UsagePanel",
    }
    assert CONTROLLED_FRONTEND_REFERENCES["message_actions.renderer"] == frozenset(
        {"feedback.FeedbackButtons"}
    )
    assert CONTROLLED_FRONTEND_REFERENCES["chat_input_panels.renderer"] == frozenset(
        {"agent_team.TeamPickerModal"}
    )
    assert CONTROLLED_FRONTEND_REFERENCES["mention_providers.provider"] == frozenset(
        {"agent_team.searchTeams"}
    )
    assert CONTROLLED_FRONTEND_REFERENCES["project_options.renderer"] == frozenset(
        {"agent_team.TeamSelectOption"}
    )
    assert CONTROLLED_FRONTEND_REFERENCES["channel_connectors.panel_renderer"] == frozenset(
        {"feishu_connector.FeishuPanel"}
    )


def test_system_plugin_package_rejects_unregistered_frontend_renderer(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "system",
        "system_plugin",
        """
id: system_plugin
name: System Plugin
version: 1.0.0
api_version: v1
""",
    )
    (folder / "frontend").mkdir()
    (folder / "frontend" / "plugin.json").write_text(
        json.dumps(
            {
                "schema": "lambchat.plugin.frontend.v1",
                "plugin_id": "system_plugin",
                "frontend": {
                    "app_panels": [
                        {
                            "id": "system_plugin:panel",
                            "tab": "feedback",
                            "renderer": "system_plugin.UnregisteredPanel",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    scan = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan()

    assert scan.descriptors[0].manifest is None
    assert "unregistered controlled host renderer/provider" in scan.errors[0]
    assert "app_panels.renderer=system_plugin.UnregisteredPanel" in scan.errors[0]


def test_user_installed_plugin_package_can_declare_future_frontend_renderer(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "future_plugin",
        """
id: future_plugin
name: Future Plugin
version: 1.0.0
api_version: v1
""",
    )
    (folder / "frontend").mkdir()
    (folder / "frontend" / "plugin.json").write_text(
        json.dumps(
            {
                "schema": "lambchat.plugin.frontend.v1",
                "plugin_id": "future_plugin",
                "frontend": {
                    "app_panels": [
                        {
                            "id": "future_plugin:panel",
                            "tab": "feedback",
                            "renderer": "future_plugin.Panel",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    scan = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan()

    assert scan.errors == ()
    assert scan.descriptors[0].manifest is not None
    assert scan.descriptors[0].manifest.frontend.app_panels[0].renderer == "future_plugin.Panel"


def test_plugin_package_scanner_rejects_foreign_structured_frontend_contribution_id(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "frontend_plugin",
        """
id: frontend_plugin
name: Frontend Plugin
version: 1.0.0
api_version: v1
""",
    )
    (folder / "frontend").mkdir()
    (folder / "frontend" / "plugin.json").write_text(
        json.dumps(
            {
                "schema": "lambchat.plugin.frontend.v1",
                "plugin_id": "frontend_plugin",
                "frontend": {
                    "message_actions": [
                        {
                            "id": "other_plugin:message-action",
                            "target": "assistant_message",
                            "renderer": "frontend_plugin.MessageAction",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    scan = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan()

    assert scan.descriptors[0].manifest is None
    assert "id must be owned by plugin frontend_plugin" in scan.errors[0]


def test_plugin_package_scanner_requires_scoped_option_settings_contract(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "frontend_plugin",
        """
id: frontend_plugin
name: Frontend Plugin
version: 1.0.0
api_version: v1
""",
    )
    (folder / "frontend").mkdir()
    (folder / "frontend" / "plugin.json").write_text(
        json.dumps(
            {
                "schema": "lambchat.plugin.frontend.v1",
                "plugin_id": "frontend_plugin",
                "frontend": {
                    "project_options": [
                        {
                            "key": "DEFAULT_ITEM_ID",
                            "type": "string",
                            "label": "frontendPlugin.defaultItem",
                        }
                    ],
                    "session_options": [
                        {
                            "key": "SELECTED_ITEM_ID",
                            "type": "string",
                            "label": "frontendPlugin.selectedItem",
                        }
                    ],
                    "channel_options": [
                        {
                            "key": "SELECTED_CHANNEL_ITEM_ID",
                            "type": "string",
                            "label": "frontendPlugin.selectedChannelItem",
                        }
                    ],
                    "scheduled_task_options": [
                        {
                            "key": "SELECTED_TASK_ITEM_ID",
                            "type": "string",
                            "label": "frontendPlugin.selectedTaskItem",
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    scan = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan()

    assert scan.descriptors[0].manifest is None
    assert "scoped frontend options must declare matching plugin settings" in scan.errors[0]
    assert "project:DEFAULT_ITEM_ID" in scan.errors[0]
    assert "session:SELECTED_ITEM_ID" in scan.errors[0]
    assert "channel:SELECTED_CHANNEL_ITEM_ID" in scan.errors[0]
    assert "scheduled_task:SELECTED_TASK_ITEM_ID" in scan.errors[0]


def test_plugin_package_scanner_compiles_frontend_asset_bundle(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "asset_plugin",
        """
id: asset_plugin
name: Asset Plugin
version: 1.0.0
api_version: v1
""",
    )
    dist = folder / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "widget.js").write_text("export const value = 1;\n", encoding="utf-8")
    (dist / "plugin-assets.json").write_text(
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

    descriptor = (
        PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan().descriptors[0]
    )

    assert descriptor.errors == ()
    assert descriptor.manifest is not None
    bundle = descriptor.manifest.package_frontend_assets
    assert bundle is not None
    assert bundle.asset_schema == "lambchat.plugin.frontend-assets.v1"
    assert bundle.slots == ["file_viewer"]
    assert bundle.assets == ["widget.js"]


def test_plugin_package_scanner_rejects_frontend_asset_bundle_for_wrong_plugin(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "asset_plugin",
        """
id: asset_plugin
name: Asset Plugin
version: 1.0.0
api_version: v1
""",
    )
    dist = folder / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "plugin-assets.json").write_text(
        json.dumps(
            {
                "plugin_id": "other_plugin",
                "asset_schema": "lambchat.plugin.frontend-assets.v1",
                "slots": ["file_viewer"],
                "assets": [],
            }
        ),
        encoding="utf-8",
    )

    scan = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan()

    assert scan.descriptors[0].manifest is None
    assert "plugin_id must match" in scan.errors[0]


def test_plugin_package_scanner_compiles_config_and_resources_files(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "folder_plugin",
        """
id: folder_plugin
name: Folder Plugin
version: 1.0.0
api_version: v1
settings:
  - key: LIMIT
    type: number
resources:
  - id: folder_plugin:legacy-resource
    type: cache_key
""",
    )
    (folder / "config").mkdir()
    (folder / "config" / "schema.json").write_text(
        json.dumps(
            {
                "settings": [
                    {
                        "key": "MODEL",
                        "type": "string",
                        "label": "Model",
                        "group": "provider",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (folder / "config" / "defaults.json").write_text(
        json.dumps({"LIMIT": 7, "MODEL": "folder-model"}),
        encoding="utf-8",
    )
    (folder / "resources").mkdir()
    (folder / "resources" / "resources.yaml").write_text(
        """
resources:
  - id: folder_plugin:data
    type: file
    scope: user
    retention_policy: keep_user_data
    cleanup_strategy: keep
""",
        encoding="utf-8",
    )

    descriptor = (
        PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan().descriptors[0]
    )

    assert descriptor.errors == ()
    manifest = descriptor.manifest
    assert manifest is not None
    assert [setting.key for setting in manifest.settings] == ["LIMIT", "MODEL"]
    assert manifest.settings[0].default == 7
    assert manifest.settings[1].default == "folder-model"
    assert manifest.package_config_defaults == {"LIMIT": 7, "MODEL": "folder-model"}
    assert {resource.id for resource in manifest.resources} == {
        "folder_plugin:legacy-resource",
        "folder_plugin:data",
    }


def test_plugin_package_scanner_rejects_mismatched_folder_id(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    _write_plugin(
        plugin_root,
        "installed",
        "folder_id",
        """
id: manifest_id
name: Bad Plugin
version: 1.0.0
api_version: v1
""",
    )

    scan = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan()

    assert scan.descriptors[0].manifest is None
    assert "folder name must match" in scan.errors[0]


def test_plugin_data_service_creates_isolated_data_dir(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "demo_plugin",
        """
id: demo_plugin
name: Demo Plugin
version: 1.0.0
api_version: v1
settings:
  - key: LIMIT
    type: number
    default: 5
""",
    )
    (folder / "plugin-data-template" / "storage").mkdir(parents=True)
    (folder / "plugin-data-template" / "storage" / "seed.txt").write_text("seed", encoding="utf-8")
    descriptor = (
        PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan().descriptors[0]
    )

    snapshot = PluginDataService(data_root=data_root).ensure_for_descriptor(descriptor)

    assert snapshot.exists is True
    assert "config" in snapshot.subdirs
    assert (data_root / "demo_plugin" / "storage" / "seed.txt").read_text(
        encoding="utf-8"
    ) == "seed"
    assert '"LIMIT": 5' in (data_root / "demo_plugin" / "config" / "defaults.json").read_text(
        encoding="utf-8"
    )


def test_plugin_data_service_audits_initialization_once(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    _write_plugin(
        plugin_root,
        "installed",
        "demo_plugin",
        """
id: demo_plugin
name: Demo Plugin
version: 1.0.0
api_version: v1
settings: []
""",
    )
    descriptor = (
        PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan().descriptors[0]
    )
    service = PluginDataService(data_root=data_root)

    service.ensure_for_descriptor(descriptor)
    service.ensure_for_descriptor(descriptor)

    audit_path = data_root / "demo_plugin" / "state" / "audit.jsonl"
    records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]

    assert [record["action"] for record in records] == ["plugin_data_initialized"]
    assert records[0]["plugin_id"] == "demo_plugin"
    assert records[0]["details"]["package_source_type"] == "installed"


def test_plugin_data_service_audits_late_template_seed_files(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "demo_plugin",
        """
id: demo_plugin
name: Demo Plugin
version: 1.0.0
api_version: v1
settings: []
""",
    )
    descriptor = (
        PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan().descriptors[0]
    )
    service = PluginDataService(data_root=data_root)
    service.ensure_for_descriptor(descriptor)

    (folder / "plugin-data-template" / "storage").mkdir(parents=True)
    (folder / "plugin-data-template" / "storage" / "later.txt").write_text("seed", encoding="utf-8")
    service.ensure_for_descriptor(descriptor)

    audit_path = data_root / "demo_plugin" / "state" / "audit.jsonl"
    records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]

    assert [record["action"] for record in records] == [
        "plugin_data_initialized",
        "plugin_data_template_seeded",
    ]
    assert records[1]["details"] == {"copied_files": ["storage/later.txt"]}


def test_plugin_data_service_uses_declared_data_template(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "demo_plugin",
        """
id: demo_plugin
name: Demo Plugin
version: 1.0.0
api_version: v1
data_template: seed-data
settings: []
""",
    )
    (folder / "seed-data" / "storage").mkdir(parents=True)
    (folder / "seed-data" / "storage" / "seed.txt").write_text("seed", encoding="utf-8")
    descriptor = (
        PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan().descriptors[0]
    )

    snapshot = PluginDataService(data_root=data_root).ensure_for_descriptor(descriptor)

    assert descriptor.errors == ()
    assert descriptor.layout.has_data_template is True
    assert descriptor.layout.data_template == "seed-data"
    assert descriptor.manifest is not None
    assert descriptor.manifest.package_data_template == "seed-data"
    assert descriptor.manifest.package_layout["data_template"] == "seed-data"
    assert snapshot.exists is True
    assert (data_root / "demo_plugin" / "storage" / "seed.txt").read_text(
        encoding="utf-8"
    ) == "seed"


def test_plugin_data_service_writes_package_config_defaults(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "demo_plugin",
        """
id: demo_plugin
name: Demo Plugin
version: 1.0.0
api_version: v1
settings:
  - key: LIMIT
    type: number
""",
    )
    (folder / "config").mkdir()
    (folder / "config" / "defaults.json").write_text('{"LIMIT": 9}\n', encoding="utf-8")
    descriptor = (
        PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan().descriptors[0]
    )

    PluginDataService(data_root=data_root).ensure_for_descriptor(descriptor)

    assert '"LIMIT": 9' in (data_root / "demo_plugin" / "config" / "defaults.json").read_text(
        encoding="utf-8"
    )


def test_plugin_data_service_reset_current_config_creates_backup(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    _write_plugin(
        plugin_root,
        "installed",
        "demo_plugin",
        """
id: demo_plugin
name: Demo Plugin
version: 1.0.0
api_version: v1
settings: []
""",
    )
    descriptor = (
        PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan().descriptors[0]
    )
    service = PluginDataService(data_root=data_root)
    service.ensure_for_descriptor(descriptor)
    current_path = data_root / "demo_plugin" / "config" / "current.json"
    current_path.write_text('{"enabled": true}\n', encoding="utf-8")

    snapshot = service.reset_current_config("demo_plugin")

    assert current_path.read_text(encoding="utf-8") == "{}\n"
    assert snapshot.backup_count == 1
    assert snapshot.last_backup_path is not None
    backup_path = Path(snapshot.last_backup_path)
    assert backup_path.parent == data_root / "demo_plugin" / "backups"
    assert backup_path.read_text(encoding="utf-8") == '{"enabled": true}\n'


def test_plugin_package_scanner_rejects_conflicting_duplicate_setting(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "demo_plugin",
        """
id: demo_plugin
name: Demo Plugin
version: 1.0.0
api_version: v1
settings:
  - key: MODEL
    type: string
    default: a
""",
    )
    (folder / "config").mkdir()
    (folder / "config" / "schema.json").write_text(
        '{"settings":[{"key":"MODEL","type":"string","default":"b"}]}',
        encoding="utf-8",
    )

    scan = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan()

    assert scan.descriptors[0].manifest is None
    assert "duplicate plugin setting" in scan.errors[0]


def test_plugin_package_scanner_rejects_scoped_option_fields_in_settings_schema(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root,
        "installed",
        "demo_plugin",
        """
id: demo_plugin
name: Demo Plugin
version: 1.0.0
api_version: v1
""",
    )
    (folder / "config").mkdir()
    (folder / "config" / "schema.json").write_text(
        json.dumps(
            {
                "settings": [
                    {
                        "key": "SELECTED_ITEM_ID",
                        "type": "string",
                        "scope": "channel",
                        "legacy_payload_keys": ["item_id"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    scan = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan()

    assert scan.descriptors[0].manifest is None
    assert "legacy_payload_keys" in scan.errors[0]
    assert "Extra inputs are not permitted" in scan.errors[0]


def test_plugin_package_scanner_rejects_bad_schema_without_blocking_other_plugins(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    bad = _write_plugin(
        plugin_root,
        "installed",
        "bad_plugin",
        """
id: bad_plugin
name: Bad Plugin
version: 1.0.0
api_version: v1
""",
    )
    (bad / "config").mkdir()
    (bad / "config" / "schema.json").write_text('{"settings": {}}', encoding="utf-8")
    _write_plugin(
        plugin_root,
        "installed",
        "good_plugin",
        """
id: good_plugin
name: Good Plugin
version: 1.0.0
api_version: v1
""",
    )

    scan = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan()

    assert len(scan.descriptors) == 2
    assert any(
        descriptor.plugin_id == "good_plugin" and descriptor.valid
        for descriptor in scan.descriptors
    )
    assert any("bad_plugin" in error and "config/schema.json" in error for error in scan.errors)


def test_builtin_folder_packages_are_complete_runtime_contracts() -> None:
    scan = PluginPackageScanner(plugin_root=Path("plugins"), data_root=Path("plugin-data")).scan()
    descriptors = {descriptor.plugin_id: descriptor for descriptor in scan.descriptors}

    assert scan.errors == ()
    assert set(descriptors) == {manifest.id for manifest in BUILTIN_PLUGIN_MANIFESTS}

    for static_manifest in BUILTIN_PLUGIN_MANIFESTS:
        descriptor = descriptors[static_manifest.id]
        package_manifest = descriptor.manifest
        assert package_manifest is not None
        assert descriptor.valid is True
        assert descriptor.layout.has_config_schema is True
        assert descriptor.layout.has_config_defaults is True
        assert descriptor.layout.has_resources is True
        assert descriptor.layout.has_frontend is True
        assert "plugin.json" in descriptor.layout.frontend_files
        assert descriptor.layout.has_data_template is True
        assert descriptor.layout.data_template == "plugin-data-template"
        data_template_dir = descriptor.folder / "plugin-data-template"
        current_template = data_template_dir / "config" / "current.json"
        defaults_template = data_template_dir / "config" / "defaults.json"
        audit_template = data_template_dir / "state" / "audit.jsonl"
        assert current_template.is_file()
        assert defaults_template.is_file()
        assert audit_template.is_file()
        assert json.loads(current_template.read_text(encoding="utf-8")) == {}
        assert (
            json.loads(defaults_template.read_text(encoding="utf-8"))
            == package_manifest.package_config_defaults
        )
        if static_manifest.routers or static_manifest.tools or static_manifest.lifespan_hooks:
            assert descriptor.layout.has_backend is True
            assert "plugin.json" in descriptor.layout.backend_files
        assert package_manifest.name == static_manifest.name
        assert package_manifest.package_manifest_authority == "folder_package"
        assert package_manifest.package_static_fallback_used is False
        assert package_manifest.package_static_fallback_fields == []
        assert package_manifest.version == static_manifest.version
        assert package_manifest.api_version == static_manifest.api_version
        assert package_manifest.install_type == static_manifest.install_type
        assert set(package_manifest.permissions) == set(static_manifest.permissions)
        assert set(package_manifest.legacy_system_settings) == set(
            static_manifest.legacy_system_settings
        )
        assert {setting.key for setting in package_manifest.settings} == {
            setting.key for setting in static_manifest.settings
        }
        assert {route.name for route in package_manifest.routers} == {
            route.name for route in static_manifest.routers
        }
        assert {tool.name for tool in package_manifest.tools} == {
            tool.name for tool in static_manifest.tools
        }
        assert {hook.name for hook in package_manifest.lifespan_hooks} == {
            hook.name for hook in static_manifest.lifespan_hooks
        }
        assert {(effect.action, effect.effect) for effect in package_manifest.runtime_effects} == {
            (effect.action, effect.effect) for effect in static_manifest.runtime_effects
        }
        assert set(package_manifest.scheduler_jobs) == set(static_manifest.scheduler_jobs)
        assert set(package_manifest.event_listeners) == set(static_manifest.event_listeners)
        assert set(package_manifest.migrations) == set(static_manifest.migrations)
        assert {(resource.type, resource.id) for resource in package_manifest.resources} == {
            (resource.type, resource.id) for resource in static_manifest.resources
        }
        assert package_manifest.frontend.model_dump(
            exclude_defaults=True
        ) == static_manifest.frontend.model_dump(exclude_defaults=True)


def test_migrated_system_plugins_do_not_use_legacy_frontend_route_fields() -> None:
    scan = PluginPackageScanner(plugin_root=Path("plugins"), data_root=Path("plugin-data")).scan()
    descriptors = scan.by_plugin_id()
    migrated_plugin_ids = {"feedback", "agent_team", "usage_reports"}

    assert scan.errors == ()
    assert migrated_plugin_ids <= set(descriptors)

    for plugin_id in migrated_plugin_ids:
        descriptor = descriptors[plugin_id]
        manifest = descriptor.manifest
        assert manifest is not None
        assert manifest.frontend.routes == []
        assert manifest.frontend.panels == []
        assert manifest.frontend.nav_items == []
        assert manifest.frontend.app_tabs != []
        assert manifest.frontend.app_panels != []

        frontend_file = descriptor.folder / "frontend" / "plugin.json"
        payload = json.loads(frontend_file.read_text(encoding="utf-8"))
        frontend = payload.get("frontend", payload)
        assert "routes" not in frontend
        assert "panels" not in frontend
        assert "nav_items" not in frontend


def test_builtin_backend_package_files_use_public_routes_key() -> None:
    scan = PluginPackageScanner(plugin_root=Path("plugins"), data_root=Path("plugin-data")).scan()

    assert scan.errors == ()
    for descriptor in scan.descriptors:
        backend_file = descriptor.folder / "backend" / "plugin.json"
        if not backend_file.is_file():
            continue
        payload = json.loads(backend_file.read_text(encoding="utf-8"))
        backend = payload.get("backend", payload)
        assert "routers" not in backend
        if descriptor.manifest and descriptor.manifest.routers:
            assert "routes" in backend


def test_folder_plugin_can_declare_metadata_only_upload_handlers(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    folder = _write_plugin(
        plugin_root / "preinstalled",
        "",
        "upload_demo",
        """
id: upload_demo
name: Upload Demo
version: 1.0.0
api_version: v1
""",
    )
    (folder / "frontend").mkdir()
    (folder / "frontend" / "plugin.json").write_text(
        json.dumps(
            {
                "upload_handlers": [
                    {
                        "id": "upload_demo:markdown-import",
                        "accept": [".md", "text/markdown"],
                        "max_bytes": 1048576,
                        "handler": "upload_demo.markdownImport",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    scan = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan()

    assert scan.errors == ()
    manifest = scan.by_plugin_id()["upload_demo"].manifest
    assert manifest is not None
    assert [item.id for item in manifest.frontend.upload_handlers] == [
        "upload_demo:markdown-import"
    ]
    assert manifest.frontend.upload_handlers[0].accept == [".md", "text/markdown"]
    assert manifest.frontend.upload_handlers[0].handler == "upload_demo.markdownImport"


def test_plugin_package_import_service_dry_run_and_installs_disabled_package_folder(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    source_root = tmp_path / "incoming"
    source = _write_plugin(
        source_root,
        "",
        "folder_plugin",
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
    )
    service = PluginPackageImportService(plugin_root=plugin_root, data_root=data_root)

    dry_run = service.import_folder(source, dry_run=True)

    assert dry_run.status == "validated"
    assert dry_run.dry_run is True
    assert not (plugin_root / "installed" / "folder_plugin").exists()

    installed = service.import_folder(source, dry_run=False)

    assert installed.status == "installed"
    assert (plugin_root / "installed" / "folder_plugin" / "plugin.yaml").is_file()
    assert (data_root / "folder_plugin" / "config" / "defaults.json").is_file()
    assert '"LIMIT": 3' in (data_root / "folder_plugin" / "config" / "defaults.json").read_text(
        encoding="utf-8"
    )
    assert installed.integrity.algorithm == "sha256:sorted-file-list-v1"
    assert len(installed.integrity.package_sha256) == 64
    assert installed.integrity.file_count >= 1
    assert installed.integrity.signature_status == "unsigned"


def test_plugin_package_import_service_accepts_zip_package(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    archive_path = tmp_path / "folder_plugin.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "folder_plugin/plugin.yaml",
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
        )

    result = PluginPackageImportService(plugin_root=plugin_root, data_root=data_root).import_folder(
        archive_path,
        dry_run=False,
    )

    assert result.status == "installed"
    assert result.source_path == str(archive_path.resolve())
    assert result.actions[0].startswith("extract archive")
    assert (plugin_root / "installed" / "folder_plugin" / "plugin.yaml").is_file()
    assert (data_root / "folder_plugin" / "config" / "defaults.json").is_file()


def test_plugin_package_lifecycle_lists_and_restores_archived_package(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    archived = plugin_root / "archived" / "folder_plugin-20260618123456"
    archived.mkdir(parents=True)
    (archived / "plugin.yaml").write_text(
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
    data_file = data_root / "folder_plugin" / "storage" / "user.txt"
    data_file.parent.mkdir(parents=True)
    data_file.write_text("existing data\n", encoding="utf-8")
    service = PluginPackageLifecycleService(plugin_root=plugin_root, data_root=data_root)

    archived_packages = service.list_archived_packages()
    restored = service.restore_archived_package("folder_plugin-20260618123456")

    assert len(archived_packages) == 1
    assert archived_packages[0].plugin_id == "folder_plugin"
    assert archived_packages[0].archived_at is not None
    assert archived_packages[0].valid is True
    assert len(archived_packages[0].integrity.package_sha256) == 64
    assert archived_packages[0].integrity.signature_status == "unsigned"
    assert restored.status == "restored"
    assert restored.plugin_id == "folder_plugin"
    assert restored.integrity.package_sha256 == archived_packages[0].integrity.package_sha256
    assert (plugin_root / "installed" / "folder_plugin" / "plugin.yaml").is_file()
    assert not archived.exists()
    assert data_file.read_text(encoding="utf-8") == "existing data\n"


def test_plugin_package_import_service_rejects_zip_path_traversal(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    archive_path = tmp_path / "bad.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "../escape/plugin.yaml", "id: escape\nname: Escape\nversion: 1.0.0\napi_version: v1\n"
        )

    with pytest.raises(ValueError, match="unsafe path|escapes"):
        PluginPackageImportService(plugin_root=plugin_root, data_root=data_root).import_folder(
            archive_path,
            dry_run=True,
        )


def test_plugin_package_import_service_rejects_folder_with_too_many_files(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(plugin_package_import, "MAX_PACKAGE_FILES", 2)
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    source = _write_plugin(
        tmp_path / "incoming",
        "",
        "folder_plugin",
        """
id: folder_plugin
name: Folder Plugin
version: 1.0.0
api_version: v1
settings: []
""",
    )
    extra = source / "storage"
    extra.mkdir()
    for index in range(3):
        (extra / f"{index}.txt").write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="too many files"):
        PluginPackageImportService(plugin_root=plugin_root, data_root=data_root).import_folder(
            source,
            dry_run=True,
        )


def test_plugin_package_import_service_rejects_folder_over_size_limit(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(plugin_package_import, "MAX_PACKAGE_BYTES", 256)
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    source = _write_plugin(
        tmp_path / "incoming",
        "",
        "folder_plugin",
        """
id: folder_plugin
name: Folder Plugin
version: 1.0.0
api_version: v1
settings: []
""",
    )
    (source / "large.bin").write_bytes(b"0" * 257)

    with pytest.raises(ValueError, match="maximum supported size"):
        PluginPackageImportService(plugin_root=plugin_root, data_root=data_root).import_folder(
            source,
            dry_run=True,
        )


def test_plugin_package_import_service_rejects_nested_folder_symlink(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    data_root = tmp_path / "plugin-data"
    source = _write_plugin(
        tmp_path / "incoming",
        "",
        "folder_plugin",
        """
id: folder_plugin
name: Folder Plugin
version: 1.0.0
api_version: v1
settings: []
""",
    )
    target = tmp_path / "outside.txt"
    target.write_text("outside", encoding="utf-8")
    link = source / "outside-link.txt"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation is not available: {exc}")

    with pytest.raises(ValueError, match="symlinks are not allowed"):
        PluginPackageImportService(plugin_root=plugin_root, data_root=data_root).import_folder(
            source,
            dry_run=True,
        )

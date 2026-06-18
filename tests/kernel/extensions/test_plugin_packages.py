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
    - name: demo_plugin.tool
      module: plugins.demo.tool
""",
    )

    scan = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan()

    assert scan.errors == ()
    assert len(scan.descriptors) == 1
    manifest = scan.manifests[0]
    assert manifest.id == "demo_plugin"
    assert manifest.install_type.value == "user_installed"
    assert manifest.package_source_type == "installed"
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
        '{"schema":"lambchat.plugin.backend.v1","plugin_id":"demo_plugin","backend":{"tools":[{"name":"demo_plugin.tool","module":"plugins.demo.tool"}]}}',
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

    descriptor = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan().descriptors[0]

    assert descriptor.layout.has_backend is True
    assert descriptor.layout.has_frontend is True
    assert descriptor.layout.has_frontend_dist is True
    assert descriptor.layout.has_config_schema is True
    assert descriptor.layout.has_resources is True
    assert descriptor.layout.has_data_template is True
    assert descriptor.layout.has_readme is True
    assert descriptor.layout.backend_files == ("plugin.json", "tools.py")
    assert descriptor.layout.frontend_files == ("dist/", "plugin.json")
    assert descriptor.manifest is not None
    assert descriptor.manifest.package_layout["has_backend"] is True
    assert descriptor.manifest.package_layout["has_frontend_dist"] is True


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
                    "tools": [
                        {
                            "name": "backend_plugin.tool",
                            "module": "plugins.backend_plugin.tools",
                            "required_permissions": ["backend_plugin:read"],
                            "legacy_ids": ["backend_tool"],
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
                    "scheduler_jobs": ["backend_plugin:job"],
                    "migrations": ["backend_plugin:migration-001"],
                },
            }
        ),
        encoding="utf-8",
    )

    descriptor = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan().descriptors[0]

    assert descriptor.errors == ()
    manifest = descriptor.manifest
    assert manifest is not None
    assert manifest.routers[0].name == "backend_plugin-api"
    assert manifest.routers[0].prefix == "/api/backend-plugin"
    assert manifest.tools[0].name == "backend_plugin.tool"
    assert manifest.tools[0].legacy_ids == ["backend_tool"]
    assert manifest.lifespan_hooks[0].name == "backend_plugin:shutdown"
    assert manifest.scheduler_jobs == ["backend_plugin:job"]
    assert manifest.migrations == ["backend_plugin:migration-001"]


def test_plugin_package_scanner_rejects_backend_plugin_file_for_wrong_plugin(tmp_path: Path) -> None:
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
                    "message_actions": ["frontend_plugin:message-action"],
                    "i18n_namespaces": ["frontend_plugin:i18n"],
                    "required_permissions": ["frontend_plugin:read"],
                },
            }
        ),
        encoding="utf-8",
    )

    descriptor = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan().descriptors[0]

    assert descriptor.errors == ()
    assert descriptor.manifest is not None
    assert descriptor.manifest.frontend.routes == ["frontend_plugin:route"]
    assert descriptor.manifest.frontend.panels == ["frontend_plugin:panel"]
    assert descriptor.manifest.frontend.nav_items == ["frontend_plugin:nav"]
    assert descriptor.manifest.frontend.message_actions == ["frontend_plugin:message-action"]
    assert descriptor.manifest.frontend.i18n_namespaces == ["frontend_plugin:i18n"]
    assert descriptor.manifest.frontend.required_permissions == ["frontend_plugin:read"]


def test_plugin_package_scanner_rejects_frontend_plugin_file_for_wrong_plugin(tmp_path: Path) -> None:
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

    descriptor = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan().descriptors[0]

    assert descriptor.errors == ()
    assert descriptor.manifest is not None
    bundle = descriptor.manifest.package_frontend_assets
    assert bundle is not None
    assert bundle.asset_schema == "lambchat.plugin.frontend-assets.v1"
    assert bundle.slots == ["file_viewer"]
    assert bundle.assets == ["widget.js"]


def test_plugin_package_scanner_rejects_frontend_asset_bundle_for_wrong_plugin(tmp_path: Path) -> None:
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

    descriptor = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan().descriptors[0]

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
    descriptor = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan().descriptors[0]

    snapshot = PluginDataService(data_root=data_root).ensure_for_descriptor(descriptor)

    assert snapshot.exists is True
    assert "config" in snapshot.subdirs
    assert (data_root / "demo_plugin" / "storage" / "seed.txt").read_text(encoding="utf-8") == "seed"
    assert '"LIMIT": 5' in (data_root / "demo_plugin" / "config" / "defaults.json").read_text(encoding="utf-8")


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
    descriptor = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan().descriptors[0]

    PluginDataService(data_root=data_root).ensure_for_descriptor(descriptor)

    assert '"LIMIT": 9' in (data_root / "demo_plugin" / "config" / "defaults.json").read_text(encoding="utf-8")


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
    descriptor = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan().descriptors[0]
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


def test_plugin_package_scanner_rejects_bad_schema_without_blocking_other_plugins(tmp_path: Path) -> None:
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
    assert any(descriptor.plugin_id == "good_plugin" and descriptor.valid for descriptor in scan.descriptors)
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
        assert descriptor.layout.has_data_template == (descriptor.folder / "plugin-data-template").is_dir()
        if static_manifest.routers or static_manifest.tools or static_manifest.lifespan_hooks:
            assert descriptor.layout.has_backend is True
            assert "plugin.json" in descriptor.layout.backend_files
        assert package_manifest.name == static_manifest.name
        assert package_manifest.version == static_manifest.version
        assert package_manifest.api_version == static_manifest.api_version
        assert package_manifest.install_type == static_manifest.install_type
        assert set(package_manifest.permissions) == set(static_manifest.permissions)
        assert set(package_manifest.legacy_system_settings) == set(static_manifest.legacy_system_settings)
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
        assert set(package_manifest.scheduler_jobs) == set(static_manifest.scheduler_jobs)
        assert set(package_manifest.migrations) == set(static_manifest.migrations)
        assert {
            (resource.type, resource.id) for resource in package_manifest.resources
        } == {(resource.type, resource.id) for resource in static_manifest.resources}
        assert package_manifest.frontend.model_dump(exclude_defaults=True) == static_manifest.frontend.model_dump(
            exclude_defaults=True
        )


def test_plugin_package_import_service_dry_run_and_installs_disabled_package_folder(tmp_path: Path) -> None:
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
    assert '"LIMIT": 3' in (data_root / "folder_plugin" / "config" / "defaults.json").read_text(encoding="utf-8")
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
        archive.writestr("../escape/plugin.yaml", "id: escape\nname: Escape\nversion: 1.0.0\napi_version: v1\n")

    with pytest.raises(ValueError, match="unsafe path|escapes"):
        PluginPackageImportService(plugin_root=plugin_root, data_root=data_root).import_folder(
            archive_path,
            dry_run=True,
        )


def test_plugin_package_import_service_rejects_folder_with_too_many_files(tmp_path: Path, monkeypatch) -> None:
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


def test_plugin_package_import_service_rejects_folder_over_size_limit(tmp_path: Path, monkeypatch) -> None:
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

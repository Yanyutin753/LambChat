"""Folder-based plugin package scanning and manifest compilation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from src.kernel.extensions.host_slots import (
    BACKEND_PLUGIN_MANIFEST_KEYS,
    CONTROLLED_FRONTEND_REFERENCE_FIELDS,
    CONTROLLED_FRONTEND_REFERENCES,
    FRONTEND_MANIFEST_CONTRIBUTION_KEYS,
    STRUCTURED_FRONTEND_MANIFEST_KEYS,
    STRUCTURED_OR_LEGACY_STRING_FRONTEND_MANIFEST_KEYS,
)
from src.kernel.extensions.manifest import (
    PluginFrontendAssetBundle,
    PluginInstallType,
    PluginManifest,
)

PluginPackageSourceType = Literal["system", "preinstalled", "installed", "staged"]


class PluginPackageBackend(BaseModel):
    model_config = ConfigDict(extra="forbid")

    routers: list[dict[str, Any]] = Field(default_factory=list)
    routes: list[dict[str, Any]] = Field(default_factory=list, exclude=True)
    agents: list[dict[str, Any]] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    lifespan_hooks: list[dict[str, Any]] = Field(default_factory=list)
    runtime_effects: list[dict[str, Any]] = Field(default_factory=list)
    scheduler_jobs: list[str] = Field(default_factory=list)
    event_listeners: list[str] = Field(default_factory=list)
    migrations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_route_alias(self) -> "PluginPackageBackend":
        """Accept public backend.routes while keeping runtime internals on routers."""
        if self.routes:
            if self.routers and self.routers != self.routes:
                raise ValueError("backend routes and routers cannot both declare different routes")
            self.routers = self.routes
        self.routes = []
        return self


class PluginPackageManifest(BaseModel):
    """Manifest stored in a plugin folder as plugin.yaml."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    api_version: str = Field(..., min_length=1)
    entrypoint: str = "backend"
    install_type: PluginInstallType | None = None
    depends_on: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    settings: list[dict[str, Any]] = Field(default_factory=list)
    legacy_system_settings: list[str] = Field(default_factory=list)
    backend: PluginPackageBackend = Field(default_factory=PluginPackageBackend)
    frontend: dict[str, Any] = Field(default_factory=dict)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    enabled_by_default: bool = True
    core: bool = False
    data_template: str = "plugin-data-template"

    def merged_with_package_files(
        self,
        *,
        backend: PluginPackageBackend,
        settings: list[dict[str, Any]],
        resources: list[dict[str, Any]],
        frontend: dict[str, Any],
    ) -> "PluginPackageManifest":
        return self.model_copy(
            update={
                "backend": backend,
                "settings": settings,
                "resources": resources,
                "frontend": frontend,
            }
        )

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("plugin package id cannot be blank")
        if any(part in {"", ".", ".."} for part in normalized.replace("\\", "/").split("/")):
            raise ValueError("plugin package id must be a safe single path segment")
        return normalized


@dataclass(frozen=True)
class PluginPackageLayout:
    has_backend: bool = False
    has_frontend: bool = False
    has_frontend_dist: bool = False
    has_config_schema: bool = False
    has_config_defaults: bool = False
    has_resources: bool = False
    has_data_template: bool = False
    data_template: str = "plugin-data-template"
    has_readme: bool = False
    backend_files: tuple[str, ...] = ()
    frontend_files: tuple[str, ...] = ()

    def model_dump(self) -> dict[str, Any]:
        return {
            "has_backend": self.has_backend,
            "has_frontend": self.has_frontend,
            "has_frontend_dist": self.has_frontend_dist,
            "has_config_schema": self.has_config_schema,
            "has_config_defaults": self.has_config_defaults,
            "has_resources": self.has_resources,
            "has_data_template": self.has_data_template,
            "data_template": self.data_template,
            "has_readme": self.has_readme,
            "backend_files": list(self.backend_files),
            "frontend_files": list(self.frontend_files),
        }


@dataclass(frozen=True)
class PluginFolderDescriptor:
    plugin_id: str
    source_type: PluginPackageSourceType
    folder: Path
    manifest_path: Path
    data_dir: Path
    validated_at: datetime
    manifest: PluginManifest | None = None
    errors: tuple[str, ...] = ()
    layout: PluginPackageLayout = field(default_factory=PluginPackageLayout)

    @property
    def valid(self) -> bool:
        return self.manifest is not None and not self.errors


@dataclass(frozen=True)
class PluginPackageScanResult:
    descriptors: tuple[PluginFolderDescriptor, ...]
    errors: tuple[str, ...] = ()

    @property
    def manifests(self) -> tuple[PluginManifest, ...]:
        return tuple(descriptor.manifest for descriptor in self.descriptors if descriptor.manifest)

    def by_plugin_id(self) -> dict[str, PluginFolderDescriptor]:
        return {descriptor.plugin_id: descriptor for descriptor in self.descriptors}


@dataclass(frozen=True)
class PluginPackageScanner:
    """Scan local plugin folders and compile them into runtime manifests."""

    plugin_root: Path
    data_root: Path
    source_dirs: dict[PluginPackageSourceType, str] = field(
        default_factory=lambda: {
            "system": "system",
            "preinstalled": "preinstalled",
            "installed": "installed",
        }
    )

    def scan(self) -> PluginPackageScanResult:
        descriptors: list[PluginFolderDescriptor] = []
        errors: list[str] = []
        seen: dict[str, Path] = {}
        for source_type, relative_dir in self.source_dirs.items():
            source_dir = self._safe_child(self.plugin_root, relative_dir)
            if not source_dir.exists():
                continue
            for folder in sorted(path for path in source_dir.iterdir() if path.is_dir()):
                descriptor = self._scan_folder(source_type, folder)
                if descriptor.plugin_id in seen:
                    descriptor = PluginFolderDescriptor(
                        plugin_id=descriptor.plugin_id,
                        source_type=descriptor.source_type,
                        folder=descriptor.folder,
                        manifest_path=descriptor.manifest_path,
                        data_dir=descriptor.data_dir,
                        validated_at=descriptor.validated_at,
                        manifest=None,
                        errors=(
                            *descriptor.errors,
                            f"duplicate plugin id already found at {seen[descriptor.plugin_id]}",
                        ),
                        layout=descriptor.layout,
                    )
                else:
                    seen[descriptor.plugin_id] = descriptor.folder
                descriptors.append(descriptor)
                errors.extend(f"{descriptor.plugin_id}: {error}" for error in descriptor.errors)
        return PluginPackageScanResult(descriptors=tuple(descriptors), errors=tuple(errors))

    def _scan_folder(
        self,
        source_type: PluginPackageSourceType,
        folder: Path,
    ) -> PluginFolderDescriptor:
        validated_at = datetime.now(UTC)
        plugin_id = folder.name
        manifest_path = folder / "plugin.yaml"
        data_dir = self._safe_child(self.data_root, plugin_id)
        errors: list[str] = []
        manifest: PluginManifest | None = None
        layout = PluginPackageLayout()
        try:
            self._ensure_inside(folder, self.plugin_root)
            if folder.is_symlink():
                raise ValueError("plugin folder symlinks are not allowed")
            if not manifest_path.is_file():
                raise ValueError("plugin.yaml is required")
            package = self._load_package_manifest(manifest_path)
            plugin_id = package.id
            data_dir = self._safe_child(self.data_root, plugin_id)
            if package.id != folder.name:
                raise ValueError("plugin folder name must match plugin.yaml id")
            self._validate_relative_path(package.entrypoint, label="entrypoint")
            self._validate_relative_path(package.data_template, label="data_template")
            layout = self._inspect_layout(folder, data_template=package.data_template)
            external_backend = self._load_package_backend(folder, plugin_id=package.id)
            external_settings, config_defaults = self._load_package_settings(folder)
            external_resources = self._load_package_resources(folder)
            external_frontend = self._load_package_frontend(
                folder,
                plugin_id=package.id,
                source_type=source_type,
            )
            frontend_assets = self._load_frontend_assets(folder, plugin_id=package.id)
            package = package.merged_with_package_files(
                backend=self._merge_backend(package.backend, external_backend),
                settings=self._merge_settings(
                    package.settings,
                    external_settings,
                    config_defaults=config_defaults,
                ),
                resources=self._merge_resources(package.resources, external_resources),
                frontend=self._merge_frontend(
                    package.frontend, external_frontend, plugin_id=package.id
                ),
            )
            manifest = self._compile_manifest(
                package,
                source_type=source_type,
                folder=folder,
                manifest_path=manifest_path,
                data_dir=data_dir,
                validated_at=validated_at,
                config_defaults=config_defaults,
                frontend_assets=frontend_assets,
            )
        except (OSError, ValidationError, ValueError) as exc:
            errors.append(str(exc) or exc.__class__.__name__)
        return PluginFolderDescriptor(
            plugin_id=plugin_id,
            source_type=source_type,
            folder=folder,
            manifest_path=manifest_path,
            data_dir=data_dir,
            validated_at=validated_at,
            manifest=manifest,
            errors=tuple(errors),
            layout=layout,
        )

    def _inspect_layout(self, folder: Path, *, data_template: str) -> PluginPackageLayout:
        backend_dir = self._safe_child(folder, "backend")
        frontend_dir = self._safe_child(folder, "frontend")
        frontend_dist_dir = self._safe_child(folder, "frontend/dist")
        return PluginPackageLayout(
            has_backend=backend_dir.is_dir(),
            has_frontend=frontend_dir.is_dir(),
            has_frontend_dist=frontend_dist_dir.is_dir(),
            has_config_schema=self._safe_child(folder, "config/schema.json").is_file(),
            has_config_defaults=self._safe_child(folder, "config/defaults.json").is_file(),
            has_resources=self._safe_child(folder, "resources/resources.yaml").is_file(),
            has_data_template=self._safe_child(folder, data_template).is_dir(),
            data_template=data_template,
            has_readme=(folder / "README.md").is_file() or (folder / "README").is_file(),
            backend_files=self._top_level_files(backend_dir),
            frontend_files=self._top_level_files(frontend_dir),
        )

    def _top_level_files(self, folder: Path) -> tuple[str, ...]:
        if not folder.is_dir():
            return ()
        values: list[str] = []
        for path in sorted(folder.iterdir()):
            if path.is_symlink():
                continue
            if path.is_file():
                values.append(path.name)
            elif path.is_dir():
                values.append(f"{path.name}/")
        return tuple(values[:20])

    def _load_package_manifest(self, manifest_path: Path) -> PluginPackageManifest:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("plugin.yaml must contain a mapping")
        return PluginPackageManifest.model_validate(raw)

    def _load_package_settings(self, folder: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        schema_path = self._optional_package_file(folder, "config/schema.json")
        defaults_path = self._optional_package_file(folder, "config/defaults.json")
        settings: list[dict[str, Any]] = []
        defaults: dict[str, Any] = {}
        if schema_path is not None:
            payload = self._load_json_file(schema_path, label="config/schema.json")
            settings = self._settings_from_schema_payload(payload)
        if defaults_path is not None:
            payload = self._load_json_file(defaults_path, label="config/defaults.json")
            if not isinstance(payload, dict):
                raise ValueError("config/defaults.json must contain a mapping")
            defaults = payload
        return settings, defaults

    def _load_package_resources(self, folder: Path) -> list[dict[str, Any]]:
        path = self._optional_package_file(folder, "resources/resources.yaml")
        if path is None:
            return []
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if payload is None:
            return []
        if isinstance(payload, list):
            resources = payload
        elif isinstance(payload, dict) and isinstance(payload.get("resources"), list):
            resources = payload["resources"]
        else:
            raise ValueError(
                "resources/resources.yaml must contain a list or a mapping with resources"
            )
        if not all(isinstance(item, dict) for item in resources):
            raise ValueError("resources/resources.yaml resources must be mappings")
        return resources

    def _load_package_backend(
        self,
        folder: Path,
        *,
        plugin_id: str,
    ) -> PluginPackageBackend:
        path = self._optional_package_file(folder, "backend/plugin.json")
        if path is None:
            return PluginPackageBackend()
        payload = self._load_json_file(path, label="backend/plugin.json")
        if not isinstance(payload, dict):
            raise ValueError("backend/plugin.json must contain a mapping")
        declared_plugin_id = payload.get("plugin_id")
        if declared_plugin_id is not None and declared_plugin_id != plugin_id:
            raise ValueError("backend/plugin.json plugin_id must match plugin.yaml id")
        schema = payload.get("schema")
        if schema is not None and schema != "lambchat.plugin.backend.v1":
            raise ValueError("backend/plugin.json schema must be lambchat.plugin.backend.v1")
        backend = payload.get("backend", payload)
        if not isinstance(backend, dict):
            raise ValueError("backend/plugin.json backend must contain a mapping")
        allowed = BACKEND_PLUGIN_MANIFEST_KEYS
        result: dict[str, Any] = {}
        for key, value in backend.items():
            if key in {"plugin_id", "schema"}:
                continue
            if key not in allowed:
                raise ValueError(f"backend/plugin.json contains unknown contribution key: {key}")
            if not isinstance(value, list):
                raise ValueError(f"backend/plugin.json {key} must be a list")
            if key in {"scheduler_jobs", "event_listeners", "migrations"}:
                if not all(isinstance(item, str) for item in value):
                    raise ValueError(f"backend/plugin.json {key} must be a list of strings")
            elif not all(isinstance(item, dict) for item in value):
                raise ValueError(f"backend/plugin.json {key} must be a list of mappings")
            result[key] = value
        return PluginPackageBackend.model_validate(result)

    def _load_package_frontend(
        self,
        folder: Path,
        *,
        plugin_id: str,
        source_type: PluginPackageSourceType,
    ) -> dict[str, Any]:
        path = self._optional_package_file(folder, "frontend/plugin.json")
        if path is None:
            return {}
        payload = self._load_json_file(path, label="frontend/plugin.json")
        if not isinstance(payload, dict):
            raise ValueError("frontend/plugin.json must contain a mapping")
        declared_plugin_id = payload.get("plugin_id")
        if declared_plugin_id is not None and declared_plugin_id != plugin_id:
            raise ValueError("frontend/plugin.json plugin_id must match plugin.yaml id")
        schema = payload.get("schema")
        if schema is not None and schema != "lambchat.plugin.frontend.v1":
            raise ValueError("frontend/plugin.json schema must be lambchat.plugin.frontend.v1")
        frontend = payload.get("frontend", payload)
        if not isinstance(frontend, dict):
            raise ValueError("frontend/plugin.json frontend must contain a mapping")
        allowed = FRONTEND_MANIFEST_CONTRIBUTION_KEYS
        structured_list_keys = STRUCTURED_FRONTEND_MANIFEST_KEYS
        structured_or_legacy_string_list_keys = STRUCTURED_OR_LEGACY_STRING_FRONTEND_MANIFEST_KEYS
        result: dict[str, Any] = {}
        for key, value in frontend.items():
            if key in {"plugin_id", "schema"}:
                continue
            if key not in allowed:
                raise ValueError(f"frontend/plugin.json contains unknown contribution key: {key}")
            if key in structured_list_keys:
                if not isinstance(value, list):
                    raise ValueError(f"frontend/plugin.json {key} must be a list")
                if not all(isinstance(item, dict) for item in value):
                    raise ValueError(f"frontend/plugin.json {key} must be a list of mappings")
            elif key in structured_or_legacy_string_list_keys:
                if not isinstance(value, list):
                    raise ValueError(f"frontend/plugin.json {key} must be a list")
                if not all(isinstance(item, (dict, str)) for item in value):
                    raise ValueError(
                        f"frontend/plugin.json {key} must be a list of mappings or strings"
                    )
            elif not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"frontend/plugin.json {key} must be a list of strings")
            result[key] = value
        self._validate_controlled_frontend_references(
            result,
            source_type=source_type,
        )
        return result

    def _validate_controlled_frontend_references(
        self,
        frontend: dict[str, Any],
        *,
        source_type: PluginPackageSourceType,
    ) -> None:
        if source_type not in {"system", "preinstalled"}:
            return
        missing: list[str] = []
        for contribution_key, fields in CONTROLLED_FRONTEND_REFERENCE_FIELDS.items():
            values = frontend.get(contribution_key, [])
            if not isinstance(values, list):
                continue
            for item in values:
                if not isinstance(item, dict):
                    continue
                for reference_field in fields:
                    reference = item.get(reference_field)
                    if not reference:
                        continue
                    contract_key = f"{contribution_key}.{reference_field}"
                    allowed = CONTROLLED_FRONTEND_REFERENCES.get(contract_key, frozenset())
                    if str(reference) not in allowed:
                        missing.append(f"{contract_key}={reference}")
        if missing:
            raise ValueError(
                "frontend/plugin.json references unregistered controlled host renderer/provider: "
                + ", ".join(missing)
            )

    def _load_frontend_assets(
        self,
        folder: Path,
        *,
        plugin_id: str,
    ) -> PluginFrontendAssetBundle | None:
        path = self._optional_package_file(folder, "frontend/dist/plugin-assets.json")
        if path is None:
            return None
        payload = self._load_json_file(path, label="frontend/dist/plugin-assets.json")
        bundle = PluginFrontendAssetBundle.model_validate(payload)
        if bundle.plugin_id != plugin_id:
            raise ValueError("frontend/dist/plugin-assets.json plugin_id must match plugin.yaml id")
        dist_dir = self._safe_child(folder, "frontend/dist")
        for asset in bundle.assets:
            self._validate_relative_path(asset, label="frontend asset")
            asset_path = (dist_dir / asset).resolve()
            self._ensure_inside(asset_path, dist_dir)
            if asset_path.is_symlink():
                raise ValueError(f"frontend asset symlinks are not allowed: {asset}")
            if not asset_path.is_file():
                raise ValueError(f"frontend asset declared but missing: {asset}")
        return bundle

    def _optional_package_file(self, folder: Path, relative_path: str) -> Path | None:
        raw_path = folder / relative_path
        if raw_path.is_symlink():
            raise ValueError(f"{relative_path} symlinks are not allowed")
        path = self._safe_child(folder, relative_path)
        if not path.exists():
            return None
        if path.is_symlink():
            raise ValueError(f"{relative_path} symlinks are not allowed")
        if not path.is_file():
            raise ValueError(f"{relative_path} must be a file")
        return path

    def _load_json_file(self, path: Path, *, label: str) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} must contain valid JSON: {exc.msg}") from exc

    def _settings_from_schema_payload(self, payload: Any) -> list[dict[str, Any]]:
        if payload is None:
            return []
        if isinstance(payload, list):
            settings = payload
        elif isinstance(payload, dict) and isinstance(payload.get("settings"), list):
            settings = payload["settings"]
        else:
            raise ValueError("config/schema.json must contain a list or a mapping with settings")
        if not all(isinstance(item, dict) for item in settings):
            raise ValueError("config/schema.json settings must be mappings")
        return settings

    def _merge_settings(
        self,
        manifest_settings: list[dict[str, Any]],
        external_settings: list[dict[str, Any]],
        *,
        config_defaults: dict[str, Any],
    ) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for setting in [*manifest_settings, *external_settings]:
            key = str(setting.get("key") or "")
            if not key:
                raise ValueError("plugin setting key cannot be blank")
            normalized = dict(setting)
            scope = str(normalized.get("scope") or "system")
            if key in config_defaults and "default" not in normalized:
                normalized["default"] = config_defaults[key]
            merge_key = (scope, key)
            existing = merged.get(merge_key)
            if existing is not None and existing != normalized:
                raise ValueError(
                    f"duplicate plugin setting with conflicting definition: {scope}:{key}"
                )
            merged[merge_key] = normalized
        return list(merged.values())

    def _merge_backend(
        self,
        manifest_backend: PluginPackageBackend,
        external_backend: PluginPackageBackend,
    ) -> PluginPackageBackend:
        return PluginPackageBackend(
            routers=self._merge_backend_mappings(
                manifest_backend.routers,
                external_backend.routers,
                key_field="name",
                label="router",
            ),
            agents=self._merge_backend_mappings(
                manifest_backend.agents,
                external_backend.agents,
                key_field="id",
                label="agent",
            ),
            tools=self._merge_backend_mappings(
                manifest_backend.tools,
                external_backend.tools,
                key_field="name",
                label="tool",
            ),
            lifespan_hooks=self._merge_backend_mappings(
                manifest_backend.lifespan_hooks,
                external_backend.lifespan_hooks,
                key_field="name",
                label="lifespan hook",
            ),
            runtime_effects=self._merge_backend_mappings(
                manifest_backend.runtime_effects,
                external_backend.runtime_effects,
                key_field="action",
                label="runtime effect",
            ),
            scheduler_jobs=self._merge_string_list(
                manifest_backend.scheduler_jobs,
                external_backend.scheduler_jobs,
                label="scheduler job",
            ),
            event_listeners=self._merge_string_list(
                manifest_backend.event_listeners,
                external_backend.event_listeners,
                label="event listener",
            ),
            migrations=self._merge_string_list(
                manifest_backend.migrations,
                external_backend.migrations,
                label="migration",
            ),
        )

    def _merge_backend_mappings(
        self,
        manifest_values: list[dict[str, Any]],
        external_values: list[dict[str, Any]],
        *,
        key_field: str,
        label: str,
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for value in [*manifest_values, *external_values]:
            key = str(value.get(key_field) or "")
            if not key:
                raise ValueError(f"plugin backend {label} {key_field} cannot be blank")
            normalized = dict(value)
            existing = merged.get(key)
            if existing is not None and existing != normalized:
                raise ValueError(
                    f"duplicate plugin backend {label} with conflicting definition: {key}"
                )
            merged[key] = normalized
        return list(merged.values())

    def _merge_string_list(
        self,
        manifest_values: list[str],
        external_values: list[str],
        *,
        label: str,
    ) -> list[str]:
        seen: set[str] = set()
        merged: list[str] = []
        for value in [*manifest_values, *external_values]:
            normalized = value.strip()
            if not normalized:
                raise ValueError(f"plugin backend {label} cannot be blank")
            if normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
        return merged

    def _merge_resources(
        self,
        manifest_resources: list[dict[str, Any]],
        external_resources: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for resource in [*manifest_resources, *external_resources]:
            resource_id = str(resource.get("id") or "")
            resource_type = str(resource.get("type") or "")
            if not resource_id or not resource_type:
                raise ValueError("plugin resource id and type cannot be blank")
            key = (resource_type, resource_id)
            normalized = dict(resource)
            existing = merged.get(key)
            if existing is not None and existing != normalized:
                raise ValueError(
                    f"duplicate plugin resource with conflicting definition: {resource_type}:{resource_id}"
                )
            merged[key] = normalized
        return list(merged.values())

    def _merge_frontend(
        self,
        manifest_frontend: dict[str, Any],
        external_frontend: dict[str, Any],
        *,
        plugin_id: str,
    ) -> dict[str, Any]:
        merged: dict[str, Any] = dict(manifest_frontend)
        for key, values in external_frontend.items():
            existing = merged.get(key, [])
            if existing is None:
                existing = []
            if not isinstance(existing, list):
                raise ValueError(f"plugin frontend {key} must be a list")
            if values and all(isinstance(item, dict) for item in values):
                if not all(isinstance(item, dict) for item in existing):
                    raise ValueError(f"plugin frontend {key} must be a list of mappings")
                merged_values = self._merge_frontend_mappings(
                    existing, values, key=key, plugin_id=plugin_id
                )
            else:
                if not all(isinstance(item, str) for item in existing):
                    raise ValueError(f"plugin frontend {key} must be a list of strings")
                seen = set(existing)
                merged_values = list(existing)
                for value in values:
                    if value in seen:
                        continue
                    seen.add(value)
                    merged_values.append(value)
            merged[key] = merged_values
        return merged

    def _merge_frontend_mappings(
        self,
        manifest_values: list[dict[str, Any]],
        external_values: list[dict[str, Any]],
        *,
        key: str,
        plugin_id: str,
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        key_field = (
            "key"
            if key
            in {"project_options", "session_options", "channel_options", "scheduled_task_options"}
            else "id"
        )
        for value in [*manifest_values, *external_values]:
            contribution_id = str(value.get(key_field) or "")
            if not contribution_id:
                raise ValueError(f"plugin frontend {key} {key_field} cannot be blank")
            if key_field == "id" and not _is_plugin_owned_contribution_id(
                contribution_id, plugin_id
            ):
                raise ValueError(
                    f"plugin frontend {key} id must be owned by plugin {plugin_id}: {contribution_id}"
                )
            normalized = dict(value)
            existing = merged.get(contribution_id)
            if existing is not None and existing != normalized:
                raise ValueError(
                    f"duplicate plugin frontend {key} with conflicting definition: {contribution_id}"
                )
            merged[contribution_id] = normalized
        return list(merged.values())

    def _compile_manifest(
        self,
        package: PluginPackageManifest,
        *,
        source_type: PluginPackageSourceType,
        folder: Path,
        manifest_path: Path,
        data_dir: Path,
        validated_at: datetime,
        config_defaults: dict[str, Any],
        frontend_assets: PluginFrontendAssetBundle | None,
    ) -> PluginManifest:
        install_type = package.install_type or _install_type_for_source(source_type)
        return PluginManifest(
            id=package.id,
            name=package.name,
            version=package.version,
            api_version=package.api_version,
            depends_on=package.depends_on,
            permissions=package.permissions,
            settings=package.settings,
            legacy_system_settings=package.legacy_system_settings,
            routers=package.backend.routers,
            agents=package.backend.agents,
            tools=package.backend.tools,
            lifespan_hooks=package.backend.lifespan_hooks,
            runtime_effects=package.backend.runtime_effects,
            scheduler_jobs=package.backend.scheduler_jobs,
            event_listeners=package.backend.event_listeners,
            migrations=package.backend.migrations,
            resources=package.resources,
            frontend=package.frontend,
            enabled_by_default=package.enabled_by_default,
            core=package.core,
            install_type=install_type,
            package_source_type=source_type,
            package_source_path=str(folder),
            package_manifest_path=str(manifest_path),
            package_data_dir=str(data_dir),
            package_validated_at=validated_at.isoformat(),
            package_config_defaults=config_defaults,
            package_data_template=package.data_template,
            package_layout=self._inspect_layout(
                folder, data_template=package.data_template
            ).model_dump(),
            package_frontend_assets=frontend_assets,
            package_manifest_authority="folder_package",
            package_static_fallback_used=False,
            package_static_fallback_fields=[],
        )

    def _safe_child(self, root: Path, child: str) -> Path:
        self._validate_relative_path(child, label="path")
        path = (root / child).resolve()
        self._ensure_inside(path, root)
        return path

    def _ensure_inside(self, path: Path, root: Path) -> None:
        resolved_root = root.resolve()
        resolved_path = path.resolve()
        try:
            resolved_path.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(f"path escapes plugin root: {path}") from exc

    def _validate_relative_path(self, value: str, *, label: str) -> None:
        normalized = value.replace("\\", "/").strip()
        if not normalized:
            raise ValueError(f"{label} cannot be blank")
        path = Path(normalized)
        if path.is_absolute() or any(part in {"..", ""} for part in path.parts):
            raise ValueError(f"{label} must be a safe relative path")


def _install_type_for_source(source_type: PluginPackageSourceType) -> PluginInstallType:
    if source_type == "system":
        return PluginInstallType.SYSTEM_BUILTIN
    if source_type in {"installed", "staged"}:
        return PluginInstallType.USER_INSTALLED
    return PluginInstallType.PREINSTALLED


def _is_plugin_owned_contribution_id(value: str, plugin_id: str) -> bool:
    return (
        value == plugin_id or value.startswith(f"{plugin_id}:") or value.startswith(f"{plugin_id}.")
    )

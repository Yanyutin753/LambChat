"""Build-time route registry for core API routes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from importlib import import_module
from pathlib import Path
from typing import Sequence, cast

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse

from src.api.routes.plugin_guard import plugin_enabled_dependency, plugin_unavailable_http_error
from src.infra.extensions.plugin_data import PluginDataService
from src.kernel.config import settings
from src.kernel.config.utils import PROJECT_ROOT
from src.kernel.extensions import (
    BUILTIN_PLUGIN_MANIFESTS,
    PluginManifest,
    PluginRouteRegistration,
    PluginRuntime,
    PluginRuntimeStatus,
)
from src.kernel.extensions.packages import (
    PluginFolderDescriptor,
    PluginPackageScanner,
    PluginPackageScanResult,
)


@dataclass(frozen=True)
class CoreRouteRegistration:
    """Declarative registration for one built-in API router."""

    id: str
    module: str
    router_name: str = "router"
    prefix: str = ""
    tags: tuple[str, ...] = ()
    core: bool = True

    def resolve_router(self) -> APIRouter:
        module = import_module(self.module)
        router = getattr(module, self.router_name)
        if not isinstance(router, APIRouter):
            raise TypeError(f"{self.module}.{self.router_name} is not an APIRouter")
        return router


CORE_ROUTE_REGISTRATIONS: tuple[CoreRouteRegistration, ...] = (
    CoreRouteRegistration("health", "src.api.routes.health", tags=("Health",)),
    CoreRouteRegistration("version", "src.api.routes.version", prefix="/api", tags=("Version",)),
    CoreRouteRegistration("chat", "src.api.routes.chat", prefix="/api/chat", tags=("Chat",)),
    CoreRouteRegistration("agent", "src.api.routes.agent", prefix="/api", tags=("Agents",)),
    CoreRouteRegistration(
        "agent_config",
        "src.api.routes.agent.config",
        prefix="/api/agent/config",
        tags=("Agent Config",),
    ),
    CoreRouteRegistration(
        "agent_models",
        "src.api.routes.agent.model",
        prefix="/api/agent/models",
        tags=("Models",),
    ),
    CoreRouteRegistration("auth", "src.api.routes.auth", prefix="/api/auth", tags=("Auth",)),
    CoreRouteRegistration("users", "src.api.routes.user", prefix="/api/users", tags=("Users",)),
    CoreRouteRegistration("roles", "src.api.routes.role", prefix="/api/roles", tags=("Roles",)),
    CoreRouteRegistration(
        "persona_presets",
        "src.api.routes.persona_preset",
        prefix="/api/persona-presets",
        tags=("Persona Presets",),
    ),
    CoreRouteRegistration(
        "sessions", "src.api.routes.session", prefix="/api/sessions", tags=("Sessions",)
    ),
    CoreRouteRegistration(
        "projects", "src.api.routes.project", prefix="/api/projects", tags=("Projects",)
    ),
    CoreRouteRegistration("share", "src.api.routes.share", prefix="/api/share", tags=("Share",)),
    CoreRouteRegistration("skills", "src.api.routes.skill", prefix="/api/skills", tags=("Skills",)),
    CoreRouteRegistration(
        "marketplace",
        "src.api.routes.marketplace",
        prefix="/api/marketplace",
        tags=("Marketplace",),
    ),
    CoreRouteRegistration(
        "plugin_runtime",
        "src.api.routes.plugin_runtime",
        prefix="/api/extensions/plugins",
        tags=("Plugin Runtime",),
    ),
    CoreRouteRegistration(
        "extension_host",
        "src.api.routes.extensions",
        prefix="/api/extensions",
        tags=("Extensions",),
    ),
    CoreRouteRegistration(
        "settings",
        "src.api.routes.settings",
        prefix="/api/settings",
        tags=("Settings",),
    ),
    CoreRouteRegistration(
        "memory", "src.api.routes.memory", prefix="/api/memory", tags=("Memory",)
    ),
    CoreRouteRegistration("mcp", "src.api.routes.mcp", prefix="/api/mcp", tags=("MCP",)),
    CoreRouteRegistration(
        "mcp_admin",
        "src.api.routes.mcp",
        router_name="admin_router",
        prefix="/api/admin/mcp",
        tags=("MCP Admin",),
    ),
    CoreRouteRegistration(
        "env_vars",
        "src.api.routes.envvar",
        prefix="/api/env-vars",
        tags=("Environment Variables",),
    ),
    CoreRouteRegistration(
        "upload", "src.api.routes.upload", prefix="/api/upload", tags=("Upload",)
    ),
    CoreRouteRegistration(
        "files", "src.api.routes.revealed_file", prefix="/api/files", tags=("Files",)
    ),
    CoreRouteRegistration("human", "src.api.routes.human", prefix="/human", tags=("Human",)),
    CoreRouteRegistration(
        "notifications",
        "src.api.routes.notification",
        prefix="/api/notifications",
        tags=("Notifications",),
    ),
    CoreRouteRegistration("push", "src.api.routes.push", prefix="/api/push", tags=("Push",)),
    CoreRouteRegistration(
        "channels", "src.api.routes.channels", prefix="/api/channels", tags=("Channels",)
    ),
    CoreRouteRegistration(
        "scheduled_tasks",
        "src.api.routes.scheduled_task",
        prefix="/api/scheduled-tasks",
        tags=("Scheduled Tasks",),
    ),
    CoreRouteRegistration("websocket", "src.api.routes.websocket", tags=("WebSocket",)),
)


def register_core_routes(
    app: FastAPI,
    registrations: Sequence[CoreRouteRegistration] = CORE_ROUTE_REGISTRATIONS,
) -> None:
    """Register built-in routes in their existing order."""
    for registration in registrations:
        app.include_router(
            registration.resolve_router(),
            prefix=registration.prefix,
            tags=list(registration.tags),
        )


def _resolve_plugin_router(registration: PluginRouteRegistration) -> APIRouter:
    module = import_module(registration.module)
    router = getattr(module, "router")
    if not isinstance(router, APIRouter):
        raise TypeError(f"{registration.module}.router is not an APIRouter")
    return router


def register_plugin_routes(
    app: FastAPI,
    runtime: PluginRuntime,
    registrations: Sequence[PluginRouteRegistration] | None = None,
) -> None:
    """Register enabled static plugin routes with a runtime guard.

    Route import/shape failures are recorded on the owning plugin and do not
    interrupt core application startup.
    """
    route_registrations = (
        list(registrations) if registrations is not None else runtime.routes(enabled_only=False)
    )
    for registration in route_registrations:
        state = runtime.get_state(registration.plugin_id)
        if state is None or state.manifest is None or state.status is PluginRuntimeStatus.ERROR:
            continue
        try:
            app.include_router(
                _resolve_plugin_router(registration),
                prefix=registration.prefix,
                tags=cast(
                    list[str | Enum], registration.tags or [f"Plugin:{registration.plugin_id}"]
                ),
                dependencies=[Depends(plugin_enabled_dependency(runtime, registration.plugin_id))],
            )
        except Exception as exc:  # noqa: BLE001 - plugin isolation boundary
            runtime.mark_error(
                registration.plugin_id,
                code="route_registration_failed",
                message=str(exc) or exc.__class__.__name__,
                phase="route_registration",
            )


def register_builtin_plugin_routes(
    app: FastAPI,
    manifests: Sequence[PluginManifest] = BUILTIN_PLUGIN_MANIFESTS,
    stored_overrides: Sequence[object] = (),
) -> PluginRuntime:
    """Register statically bundled business plugins and expose their runtime state."""
    scan_result, data_service, runtime_manifests = _build_runtime_manifests_with_packages(manifests)
    runtime = PluginRuntime(runtime_manifests, core_dependencies=("skill_core",))
    for override in stored_overrides:
        plugin_id = getattr(override, "plugin_id", None)
        status = getattr(override, "status", None)
        if not plugin_id or status is None:
            continue
        try:
            runtime.apply_stored_status(
                plugin_id,
                status,
                updated_at=getattr(override, "updated_at", None),
                updated_by=getattr(override, "updated_by", None),
            )
        except Exception:  # noqa: BLE001 - invalid persisted state must not break startup
            continue
    register_plugin_routes(app, runtime)
    register_plugin_asset_routes(app, runtime)
    app.state.plugin_runtime = runtime
    app.state.plugin_package_scan = scan_result
    app.state.plugin_data_service = data_service
    return runtime


def register_plugin_asset_routes(app: FastAPI, runtime: PluginRuntime) -> None:
    """Expose built plugin frontend assets from local package folders.

    This serves only already-built static files under a package's
    ``frontend/dist`` directory and is guarded by Plugin Runtime state.
    """

    @app.get("/plugin-assets/{plugin_id}/{asset_path:path}")
    async def serve_plugin_asset(plugin_id: str, asset_path: str):
        state = runtime.get_state(plugin_id)
        if state is None or state.manifest is None:
            raise HTTPException(status_code=404, detail="plugin asset not found")
        try:
            runtime.ensure_enabled(plugin_id)
        except Exception as exc:
            raise plugin_unavailable_http_error(plugin_id, exc) from exc
        package_source_path = state.manifest.package_source_path
        if not package_source_path:
            raise HTTPException(status_code=404, detail="plugin asset not found")
        dist_dir = (Path(package_source_path) / "frontend" / "dist").resolve()
        if not dist_dir.is_dir():
            raise HTTPException(status_code=404, detail="plugin asset not found")
        if any(part in {"", ".", ".."} for part in asset_path.replace("\\", "/").split("/")):
            raise HTTPException(status_code=404, detail="plugin asset not found")
        asset_file = (dist_dir / asset_path).resolve()
        try:
            asset_file.relative_to(dist_dir)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="plugin asset not found") from exc
        if not asset_file.is_file():
            raise HTTPException(status_code=404, detail="plugin asset not found")
        return FileResponse(str(asset_file))


def _build_runtime_manifests_with_packages(
    manifests: Sequence[PluginManifest],
) -> tuple[PluginPackageScanResult, PluginDataService, tuple[PluginManifest, ...]]:
    plugin_root = _configured_path(settings.PLUGIN_PACKAGE_PATH)
    data_root = _configured_path(settings.PLUGIN_DATA_PATH)
    scanner = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root)
    scan_result = scanner.scan()
    data_service = PluginDataService(data_root=data_root)
    descriptors = scan_result.by_plugin_id()
    static_ids = {manifest.id for manifest in manifests}
    runtime_manifests: list[PluginManifest] = []
    for manifest in manifests:
        descriptor = descriptors.get(manifest.id)
        if descriptor is not None:
            manifest = _attach_package_descriptor(manifest, descriptor)
            data_service.ensure_for_descriptor(_descriptor_with_manifest(descriptor, manifest))
        runtime_manifests.append(manifest)
    for descriptor in scan_result.descriptors:
        if descriptor.plugin_id in static_ids or descriptor.manifest is None:
            continue
        data_service.ensure_for_descriptor(descriptor)
        runtime_manifests.append(descriptor.manifest)
    return scan_result, data_service, tuple(runtime_manifests)


def _attach_package_descriptor(
    manifest: PluginManifest,
    descriptor: PluginFolderDescriptor,
) -> PluginManifest:
    package_manifest = descriptor.manifest
    if package_manifest is not None:
        return _package_manifest_with_static_fallback(
            package_manifest,
            static_manifest=manifest,
            descriptor=descriptor,
        )
    update = {
        "package_source_type": descriptor.source_type,
        "package_source_path": str(descriptor.folder),
        "package_manifest_path": str(descriptor.manifest_path),
        "package_data_dir": str(descriptor.data_dir),
        "package_validated_at": descriptor.validated_at.isoformat(),
        "package_errors": list(descriptor.errors),
        "package_data_template": descriptor.layout.data_template,
        "package_layout": descriptor.layout.model_dump(),
    }
    return manifest.model_copy(
        update=update,
    )


def _package_manifest_with_static_fallback(
    package_manifest: PluginManifest,
    *,
    static_manifest: PluginManifest,
    descriptor: PluginFolderDescriptor,
) -> PluginManifest:
    """Use the folder package as the authoritative built-in declaration."""
    fallback_fields = _static_fallback_fields(package_manifest, static_manifest)
    return package_manifest.model_copy(
        update={
            "package_source_type": descriptor.source_type,
            "package_source_path": str(descriptor.folder),
            "package_manifest_path": str(descriptor.manifest_path),
            "package_data_dir": str(descriptor.data_dir),
            "package_validated_at": descriptor.validated_at.isoformat(),
            "package_errors": list(descriptor.errors),
            "package_layout": descriptor.layout.model_dump(),
            "package_config_defaults": package_manifest.package_config_defaults,
            "package_data_template": package_manifest.package_data_template,
            "package_frontend_assets": package_manifest.package_frontend_assets,
            "package_manifest_authority": "folder_package",
            "package_static_fallback_used": bool(fallback_fields),
            "package_static_fallback_fields": fallback_fields,
        }
    )


def _static_fallback_fields(
    package_manifest: PluginManifest,
    static_manifest: PluginManifest,
) -> list[str]:
    fields: list[str] = []
    if not package_manifest.settings and static_manifest.settings:
        fields.append("settings")
    if not package_manifest.legacy_system_settings and static_manifest.legacy_system_settings:
        fields.append("legacy_system_settings")
    if not package_manifest.routers and static_manifest.routers:
        fields.append("routers")
    if not package_manifest.tools and static_manifest.tools:
        fields.append("tools")
    if not package_manifest.lifespan_hooks and static_manifest.lifespan_hooks:
        fields.append("lifespan_hooks")
    if not package_manifest.scheduler_jobs and static_manifest.scheduler_jobs:
        fields.append("scheduler_jobs")
    if not package_manifest.event_listeners and static_manifest.event_listeners:
        fields.append("event_listeners")
    if not package_manifest.migrations and static_manifest.migrations:
        fields.append("migrations")
    if not package_manifest.resources and static_manifest.resources:
        fields.append("resources")
    if not package_manifest.frontend.model_dump(
        exclude_defaults=True
    ) and static_manifest.frontend.model_dump(exclude_defaults=True):
        fields.append("frontend")
    return fields


def _merge_manifest_resources(
    manifest: PluginManifest,
    package_manifest: PluginManifest,
) -> list[object]:
    merged: dict[tuple[str, str], object] = {}
    for resource in [*manifest.resources, *package_manifest.resources]:
        resource_type = getattr(resource, "type", "")
        resource_id = getattr(resource, "id", "")
        key = (str(resource_type), str(resource_id))
        if key not in merged:
            merged[key] = resource
    return list(merged.values())


def _merge_manifest_frontend(
    manifest: PluginManifest,
    package_manifest: PluginManifest,
) -> object:
    values = manifest.frontend.model_dump()
    package_values = package_manifest.frontend.model_dump()
    for key, package_list in package_values.items():
        existing = values.get(key, []) or []
        seen = set(existing)
        merged = list(existing)
        for item in package_list or []:
            if item in seen:
                continue
            seen.add(item)
            merged.append(item)
        values[key] = merged
    return manifest.frontend.model_copy(update=values)


def _descriptor_with_manifest(
    descriptor: PluginFolderDescriptor,
    manifest: PluginManifest,
) -> PluginFolderDescriptor:
    return PluginFolderDescriptor(
        plugin_id=descriptor.plugin_id,
        source_type=descriptor.source_type,
        folder=descriptor.folder,
        manifest_path=descriptor.manifest_path,
        data_dir=descriptor.data_dir,
        validated_at=descriptor.validated_at,
        manifest=manifest,
        errors=descriptor.errors,
        layout=descriptor.layout,
    )


def _configured_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()

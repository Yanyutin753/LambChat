"""Read-only Plugin Runtime observability routes."""

from __future__ import annotations

import io
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.api.deps import require_permissions
from src.api.plugin_lifecycle import run_plugin_lifecycle_hooks
from src.api.routes.plugin_runtime_helpers import (
    _audit_response,
    _dry_run_package_data_policy,
    _dry_run_response_dict,
    _manifest_data_template_summary,
    _manifest_export,
    _package_archive_bytes,
    _package_data_policy,
    _package_summary,
    _runtime_capabilities,
)
from src.api.routes.plugin_runtime_models import (
    ArchivedPluginPackageResponse,
    ArchivedPluginPackagesResponse,
    PluginDataResponse,
    PluginDryRunResourceResponse,
    PluginExportResponse,
    PluginImportRequest,
    PluginImportResponse,
    PluginPackageDescriptorResponse,
    PluginPackageExportResponse,
    PluginPackageImportRequest,
    PluginPackageImportResponse,
    PluginPackageRestoreResponse,
    PluginPackageReviewRequest,
    PluginPackageReviewResponse,
    PluginPackagesResponse,
    PluginResourceRecordResponse,
    PluginResourcesResponse,
    PluginRuntimeAgentResponse,
    PluginRuntimeAuditResponse,
    PluginRuntimeContributionStateResponse,
    PluginRuntimeContributionStatesResponse,
    PluginRuntimeEffectResponse,
    PluginRuntimeFrontendResponse,
    PluginRuntimeIssueResponse,
    PluginRuntimeListResponse,
    PluginRuntimePackageResponse,
    PluginRuntimePluginResponse,
    PluginRuntimeRouteResponse,
    PluginRuntimeSideEffectResponse,
    PluginRuntimeToolResponse,
    PluginSettingGroupResponse,
    PluginSettingResponse,
    PluginSettingsResponse,
    PluginSettingUpdate,
    PluginUninstallDryRunResponse,
    PluginUninstallRequest,
    PluginUninstallResponse,
)
from src.infra.extensions import (
    PluginDataSnapshot,
    PluginPackageImportService,
    PluginPackageLifecycleService,
    PluginPackageReviewRecord,
    PluginSettingsService,
    build_package_integrity,
    get_plugin_runtime_state_storage,
    get_plugin_settings_service,
)
from src.infra.extensions.plugin_data import PluginDataService as PluginDataServiceClass
from src.infra.logging import get_logger
from src.kernel.config import settings
from src.kernel.extensions import (
    BUILTIN_PLUGIN_MANIFESTS,
    PluginResourceRecord,
    PluginRuntime,
    PluginRuntimeIssue,
    PluginRuntimeState,
    PluginRuntimeStateTransitionError,
    PluginRuntimeStatus,
    PluginRuntimeUninstallError,
    build_uninstall_dry_run,
    validate_uninstall_dry_run,
)
from src.kernel.extensions.packages import PluginFolderDescriptor, PluginPackageScanner

router = APIRouter()
logger = get_logger(__name__)


def _get_runtime(request: Request) -> PluginRuntime:
    runtime = getattr(request.app.state, "plugin_runtime", None)
    if isinstance(runtime, PluginRuntime):
        return runtime
    return PluginRuntime(BUILTIN_PLUGIN_MANIFESTS, core_dependencies=("skill_core",))


def _get_state_storage(request: Request):
    storage = getattr(request.app.state, "plugin_runtime_state_storage", None)
    return storage or get_plugin_runtime_state_storage()


def _get_data_service(request: Request) -> PluginDataServiceClass:
    service = getattr(request.app.state, "plugin_data_service", None)
    if isinstance(service, PluginDataServiceClass):
        return service
    _, data_root = _configured_plugin_roots()
    return PluginDataServiceClass(data_root=data_root)


def _get_package_lifecycle_service(request: Request) -> PluginPackageLifecycleService:
    service = getattr(request.app.state, "plugin_package_lifecycle_service", None)
    if isinstance(service, PluginPackageLifecycleService):
        return service
    plugin_root, data_root = _configured_plugin_roots()
    return PluginPackageLifecycleService(plugin_root=plugin_root, data_root=data_root)


def _configured_plugin_roots() -> tuple[Path, Path]:
    from src.kernel.config.utils import PROJECT_ROOT

    plugin_root = Path(getattr(settings, "PLUGIN_PACKAGE_PATH", "./plugins"))
    if not plugin_root.is_absolute():
        plugin_root = PROJECT_ROOT / plugin_root
    data_root = Path(getattr(settings, "PLUGIN_DATA_PATH", "./plugin-data"))
    if not data_root.is_absolute():
        data_root = PROJECT_ROOT / data_root
    return plugin_root, data_root


def _plugin_packages_response(request: Request) -> PluginPackagesResponse:
    scan = getattr(request.app.state, "plugin_package_scan", None)
    descriptors = list(getattr(scan, "descriptors", []) or [])
    errors = list(getattr(scan, "errors", []) or [])
    plugin_root = None
    data_root = None
    if descriptors:
        plugin_root = str(descriptors[0].folder.parent.parent)
        data_root = str(descriptors[0].data_dir.parent)
    return PluginPackagesResponse(
        plugin_root=plugin_root,
        data_root=data_root,
        packages=[
            PluginPackageDescriptorResponse(
                plugin_id=descriptor.plugin_id,
                source_type=descriptor.source_type,
                folder=str(descriptor.folder),
                manifest_path=str(descriptor.manifest_path),
                data_dir=str(descriptor.data_dir),
                validated_at=descriptor.validated_at,
                valid=descriptor.valid,
                errors=list(descriptor.errors),
                layout=descriptor.layout.model_dump(),
            )
            for descriptor in descriptors
        ],
        errors=errors,
        total=len(descriptors),
    )


def _descriptor_with_manifest(
    descriptor: PluginFolderDescriptor, manifest
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


async def _refresh_runtime_from_packages(
    request: Request, *, plugin_root, data_root
) -> PluginRuntime:
    scan = PluginPackageScanner(plugin_root=plugin_root, data_root=data_root).scan()
    data_service = PluginDataServiceClass(data_root=data_root)
    descriptors = scan.by_plugin_id()
    static_ids = {manifest.id for manifest in BUILTIN_PLUGIN_MANIFESTS}
    runtime_manifests = []
    for manifest in BUILTIN_PLUGIN_MANIFESTS:
        descriptor = descriptors.get(manifest.id)
        if descriptor is not None:
            if descriptor.manifest is not None:
                manifest = _package_manifest_with_static_fallback(
                    descriptor.manifest,
                    static_manifest=manifest,
                    descriptor=descriptor,
                )
            else:
                manifest = _attach_descriptor_metadata(manifest, descriptor)
            data_service.ensure_for_descriptor(_descriptor_with_manifest(descriptor, manifest))
        runtime_manifests.append(manifest)
    for descriptor in scan.descriptors:
        if descriptor.plugin_id in static_ids or descriptor.manifest is None:
            continue
        data_service.ensure_for_descriptor(descriptor)
        runtime_manifests.append(descriptor.manifest)
    runtime = PluginRuntime(runtime_manifests, core_dependencies=("skill_core",))
    storage = _get_state_storage(request)
    for override in await storage.list_overrides():
        try:
            runtime.apply_stored_status(
                override.plugin_id,
                override.status,
                updated_at=override.updated_at,
                updated_by=override.updated_by,
            )
        except Exception:  # noqa: BLE001 - stale overrides must not break package scans
            continue
    request.app.state.plugin_package_scan = scan
    request.app.state.plugin_data_service = data_service
    request.app.state.plugin_runtime = runtime
    return runtime


def _attach_descriptor_metadata(manifest, descriptor: PluginFolderDescriptor):
    return manifest.model_copy(
        update={
            "package_source_type": descriptor.source_type,
            "package_source_path": str(descriptor.folder),
            "package_manifest_path": str(descriptor.manifest_path),
            "package_data_dir": str(descriptor.data_dir),
            "package_validated_at": descriptor.validated_at.isoformat(),
            "package_errors": list(descriptor.errors),
            "package_layout": descriptor.layout.model_dump(),
            "package_data_template": descriptor.layout.data_template,
        }
    )


def _package_manifest_with_static_fallback(package_manifest, *, static_manifest, descriptor):
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


def _static_fallback_fields(package_manifest, static_manifest) -> list[str]:
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


def _merge_manifest_resources(manifest, package_manifest) -> list[object]:
    merged: dict[tuple[str, str], object] = {}
    for resource in [*manifest.resources, *package_manifest.resources]:
        resource_type = getattr(resource, "type", "")
        resource_id = getattr(resource, "id", "")
        key = (str(resource_type), str(resource_id))
        if key not in merged:
            merged[key] = resource
    return list(merged.values())


def _merge_manifest_frontend(manifest, package_manifest) -> object:
    values = manifest.frontend.model_dump()
    package_values = package_manifest.frontend.model_dump()
    for key, package_list in package_values.items():
        existing = values.get(key, []) or []
        merged = list(existing)
        if package_list and all(isinstance(item, dict) for item in package_list):
            seen = {str(item.get("id") or "") for item in existing if isinstance(item, dict)}
            for item in package_list or []:
                contribution_id = str(item.get("id") or "") if isinstance(item, dict) else ""
                if contribution_id in seen:
                    continue
                seen.add(contribution_id)
                merged.append(item)
            values[key] = merged
            continue
        seen = set(existing)
        for item in package_list or []:
            if item in seen:
                continue
            seen.add(item)
            merged.append(item)
        values[key] = merged
    return manifest.frontend.model_copy(update=values)


def _package_descriptor_response(descriptor) -> PluginPackageDescriptorResponse:
    return PluginPackageDescriptorResponse(
        plugin_id=descriptor.plugin_id,
        source_type=descriptor.source_type,
        folder=str(descriptor.folder),
        manifest_path=str(descriptor.manifest_path),
        data_dir=str(descriptor.data_dir),
        validated_at=descriptor.validated_at,
        valid=descriptor.valid,
        errors=list(descriptor.errors),
        layout=descriptor.layout.model_dump(),
    )


def _archived_package_response(item) -> ArchivedPluginPackageResponse:
    return ArchivedPluginPackageResponse(
        archive_id=item.archive_id,
        plugin_id=item.plugin_id,
        archive_path=item.archive_path,
        manifest_path=item.manifest_path,
        data_dir=item.data_dir,
        archived_at=item.archived_at,
        integrity=item.integrity.model_dump(),
        valid=item.valid,
        errors=item.errors,
    )


def _frontend_response(manifest) -> PluginRuntimeFrontendResponse:
    return PluginRuntimeFrontendResponse(
        routes=manifest.frontend.routes,
        panels=manifest.frontend.panels,
        nav_items=manifest.frontend.nav_items,
        app_tabs=[item.model_dump(mode="json") for item in manifest.frontend.app_tabs],
        app_panels=[item.model_dump(mode="json") for item in manifest.frontend.app_panels],
        sidebar_items=[item.model_dump(mode="json") for item in manifest.frontend.sidebar_items],
        user_menu_items=[
            item.model_dump(mode="json") for item in manifest.frontend.user_menu_items
        ],
        tool_renderers=[item.model_dump(mode="json") for item in manifest.frontend.tool_renderers],
        file_viewers=[item.model_dump(mode="json") for item in manifest.frontend.file_viewers],
        upload_handlers=[
            item.model_dump(mode="json") for item in manifest.frontend.upload_handlers
        ],
        skill_importers=[
            item.model_dump(mode="json") for item in manifest.frontend.skill_importers
        ],
        channel_connectors=[
            item.model_dump(mode="json") for item in manifest.frontend.channel_connectors
        ],
        message_actions=[
            item.model_dump(mode="json") for item in manifest.frontend.message_actions
        ],
        chat_input_options=[
            item.model_dump(mode="json") for item in manifest.frontend.chat_input_options
        ],
        chat_input_panels=[
            item.model_dump(mode="json") for item in manifest.frontend.chat_input_panels
        ],
        mention_providers=[
            item.model_dump(mode="json") for item in manifest.frontend.mention_providers
        ],
        welcome_surfaces=[
            item.model_dump(mode="json") for item in manifest.frontend.welcome_surfaces
        ],
        assistant_identity_resolvers=[
            item.model_dump(mode="json") for item in manifest.frontend.assistant_identity_resolvers
        ],
        agent_categories=[
            item.model_dump(mode="json") for item in manifest.frontend.agent_categories
        ],
        project_options=[
            item.model_dump(mode="json") for item in manifest.frontend.project_options
        ],
        session_options=[
            item.model_dump(mode="json") for item in manifest.frontend.session_options
        ],
        channel_options=[
            item.model_dump(mode="json") for item in manifest.frontend.channel_options
        ],
        scheduled_task_options=[
            item.model_dump(mode="json") for item in manifest.frontend.scheduled_task_options
        ],
        settings_sections=manifest.frontend.settings_sections,
        i18n_namespaces=manifest.frontend.i18n_namespaces,
        required_permissions=manifest.frontend.required_permissions,
    )


def _empty_frontend_response() -> PluginRuntimeFrontendResponse:
    return PluginRuntimeFrontendResponse(
        routes=[],
        panels=[],
        nav_items=[],
        app_tabs=[],
        app_panels=[],
        sidebar_items=[],
        user_menu_items=[],
        tool_renderers=[],
        file_viewers=[],
        upload_handlers=[],
        skill_importers=[],
        channel_connectors=[],
        message_actions=[],
        chat_input_options=[],
        chat_input_panels=[],
        mention_providers=[],
        welcome_surfaces=[],
        assistant_identity_resolvers=[],
        agent_categories=[],
        project_options=[],
        session_options=[],
        channel_options=[],
        scheduled_task_options=[],
        settings_sections=[],
        i18n_namespaces=[],
        required_permissions=[],
    )


def _resource_type_counts(records: list[PluginResourceRecord]) -> dict[str, int]:
    return dict(Counter(record.resource_type.value for record in records))


def _issue_response(issue: PluginRuntimeIssue) -> PluginRuntimeIssueResponse:
    return PluginRuntimeIssueResponse(
        plugin_id=issue.plugin_id,
        code=issue.code,
        message=issue.message,
        phase=issue.phase,
    )


def _default_runtime_side_effect(plugin_id: str) -> PluginRuntimeSideEffectResponse:
    manifest = next(
        (item for item in BUILTIN_PLUGIN_MANIFESTS if item.id == plugin_id),
        None,
    )
    if manifest and manifest.runtime_effects:
        return PluginRuntimeSideEffectResponse(
            action="none",
            status="available",
            message="Runtime side effects are declared for this plugin and available during runtime state changes.",
        )
    return PluginRuntimeSideEffectResponse(
        action="none",
        status="not_applicable",
        message="No runtime side effect is registered for this static plugin.",
    )


def _state_response(
    runtime: PluginRuntime,
    state: PluginRuntimeState,
    *,
    runtime_side_effect: PluginRuntimeSideEffectResponse | None = None,
) -> PluginRuntimePluginResponse:
    manifest = state.manifest
    resources = runtime.resource_ledger.list(plugin_id=state.plugin_id)
    dry_run = build_uninstall_dry_run(plugin_id=state.plugin_id, ledger=runtime.resource_ledger)
    dry_run_actions = Counter(resource.action.value for resource in dry_run.resources)

    return PluginRuntimePluginResponse(
        plugin_id=state.plugin_id,
        name=manifest.name if manifest else None,
        description=manifest.description if manifest else None,
        version=manifest.version if manifest else None,
        api_version=manifest.api_version if manifest else None,
        status=state.status.value,
        state_source=state.state_source,
        state_updated_at=state.state_updated_at,
        state_updated_by=state.state_updated_by,
        enabled=state.enabled,
        executable=state.executable,
        core=manifest.core if manifest else False,
        install_type=manifest.install_type.value if manifest else "not_installed",
        uninstallable=manifest.uninstallable if manifest else False,
        depends_on=manifest.depends_on if manifest else [],
        permissions=manifest.declared_permissions() if manifest else [],
        routes=[
            PluginRuntimeRouteResponse(
                name=route.name,
                prefix=route.prefix,
                module=route.module,
                required_permissions=route.required_permissions,
                tags=route.tags,
            )
            for route in (manifest.routers if manifest else [])
        ],
        agents=[
            PluginRuntimeAgentResponse(
                id=agent.id,
                module=agent.module,
                name=agent.name,
                description=agent.description,
                icon=agent.icon,
                sort_order=agent.sort_order,
                category=agent.category,
                required_permissions=agent.required_permissions,
            )
            for agent in (manifest.agents if manifest else [])
        ],
        tools=[
            PluginRuntimeToolResponse(
                name=tool.name,
                module=tool.module,
                required_permissions=tool.required_permissions,
                legacy_ids=tool.legacy_ids,
            )
            for tool in (manifest.tools if manifest else [])
        ],
        runtime_effects=[
            PluginRuntimeEffectResponse(action=item.action, effect=item.effect)
            for item in (manifest.runtime_effects if manifest else [])
        ],
        frontend=_frontend_response(manifest) if manifest else _empty_frontend_response(),
        resource_count=len(resources),
        resource_types=_resource_type_counts(resources),
        dry_run_actions=dict(dry_run_actions),
        runtime_side_effect=runtime_side_effect or _default_runtime_side_effect(state.plugin_id),
        package=PluginRuntimePackageResponse(
            source_type=manifest.package_source_type if manifest else "not_installed",
            manifest_authority=(
                manifest.package_manifest_authority if manifest else "static_manifest"
            ),
            static_fallback_used=(manifest.package_static_fallback_used if manifest else False),
            static_fallback_fields=(manifest.package_static_fallback_fields if manifest else []),
            source_path=manifest.package_source_path if manifest else None,
            manifest_path=manifest.package_manifest_path if manifest else None,
            data_dir=manifest.package_data_dir if manifest else None,
            validated_at=manifest.package_validated_at if manifest else None,
            errors=manifest.package_errors if manifest else [],
            layout=manifest.package_layout if manifest else {},
            frontend_assets=(
                manifest.package_frontend_assets.model_dump(mode="json")
                if manifest and manifest.package_frontend_assets
                else None
            ),
            data_template=_manifest_data_template_summary(manifest),
            data_policy=_package_data_policy(manifest) if manifest else {},
        ),
        issues=[_issue_response(issue) for issue in state.issues],
    )


def _contribution_state_response(
    state: PluginRuntimeState,
) -> PluginRuntimeContributionStateResponse:
    manifest = state.manifest
    return PluginRuntimeContributionStateResponse(
        plugin_id=state.plugin_id,
        enabled=state.enabled,
        executable=state.executable,
        status=state.status.value,
        agents=[
            PluginRuntimeAgentResponse(
                id=agent.id,
                module=agent.module,
                name=agent.name,
                description=agent.description,
                icon=agent.icon,
                sort_order=agent.sort_order,
                category=agent.category,
                required_permissions=agent.required_permissions,
            )
            for agent in (manifest.agents if manifest else [])
        ],
        tools=[
            PluginRuntimeToolResponse(
                name=tool.name,
                module=tool.module,
                required_permissions=tool.required_permissions,
                legacy_ids=tool.legacy_ids,
            )
            for tool in (manifest.tools if manifest else [])
        ],
        frontend=_frontend_response(manifest) if manifest else None,
    )


def _resource_response(record: PluginResourceRecord) -> PluginResourceRecordResponse:
    return PluginResourceRecordResponse(
        plugin_id=record.plugin_id,
        resource_id=record.resource_id,
        resource_type=record.resource_type.value,
        scope=record.scope.value,
        owner_user_id=record.owner_user_id,
        owner_role=record.owner_role,
        created_by_plugin_version=record.created_by_plugin_version,
        retention_policy=record.retention_policy.value,
        cleanup_strategy=record.cleanup_strategy.value,
        created_at=record.created_at,
        updated_at=record.updated_at,
        last_seen_at=record.last_seen_at,
        metadata=record.metadata,
    )


def _require_state(runtime: PluginRuntime, plugin_id: str) -> PluginRuntimeState:
    state = runtime.get_state(plugin_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    return state


def _state_transition_error(exc: PluginRuntimeStateTransitionError) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"error": "plugin_state_transition_rejected", "message": str(exc)},
    )


def _uninstall_error(exc: PluginRuntimeUninstallError) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"error": "plugin_uninstall_rejected", "message": str(exc)},
    )


def _installed_package_integrity(state: PluginRuntimeState):
    manifest = state.manifest
    if manifest is None or manifest.package_source_type != "installed":
        return None
    if not manifest.package_source_path:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "plugin_package_integrity_required",
                "message": "User-installed plugins require local package integrity metadata before enable.",
            },
        )
    package_path = Path(manifest.package_source_path)
    if not package_path.exists():
        raise HTTPException(
            status_code=409,
            detail={
                "error": "plugin_package_missing",
                "message": "The installed plugin package folder is missing.",
                "plugin_id": state.plugin_id,
            },
        )
    return build_package_integrity(package_path)


async def _plugin_enable_integrity_blocker(
    state: PluginRuntimeState,
    storage,
) -> dict[str, Any] | None:
    integrity = _installed_package_integrity(state)
    if integrity is None:
        return None
    if not integrity.signed:
        review = await storage.get_package_review(
            plugin_id=state.plugin_id,
            package_sha256=integrity.package_sha256,
        )
        if review is not None:
            return None
        return {
            "error": "plugin_package_unsigned",
            "message": "User-installed plugin packages must remain disabled until the current package hash is locally reviewed or signature verification succeeds.",
            "plugin_id": state.plugin_id,
            "signature_status": integrity.signature_status,
            "package_sha256": integrity.package_sha256,
            "file_count": integrity.file_count,
            "total_bytes": integrity.total_bytes,
        }
    return None


def _package_review_response(
    *,
    plugin_id: str,
    integrity,
    review: PluginPackageReviewRecord | None,
) -> PluginPackageReviewResponse:
    return PluginPackageReviewResponse(
        plugin_id=plugin_id,
        package_sha256=integrity.package_sha256,
        reviewed_at=review.reviewed_at if review else None,
        reviewed_by=review.reviewed_by if review else None,
        reviewer_username=review.reviewer_username if review else None,
        reason=review.reason if review else None,
        active_for_current_package=review is not None,
        integrity=integrity.model_dump(),
    )


def _settings_service(request: Request) -> PluginSettingsService:
    service = getattr(request.app.state, "plugin_settings_service", None)
    return service if isinstance(service, PluginSettingsService) else get_plugin_settings_service()


async def _plugin_settings_response(
    *,
    state: PluginRuntimeState,
    service: PluginSettingsService,
    scope: str = "system",
    subject_id: str | None = None,
) -> PluginSettingsResponse:
    manifest = state.manifest
    if manifest is None:
        raise HTTPException(status_code=409, detail="plugin manifest is unavailable")
    settings = await service.list_settings(
        manifest,
        scope=scope,
        subject_id=subject_id,
    )
    groups = Counter(item["group"] for item in settings)
    return PluginSettingsResponse(
        plugin_id=state.plugin_id,
        plugin_status=state.status.value,
        plugin_executable=state.executable,
        settings=[PluginSettingResponse(**item) for item in settings],
        groups=[
            PluginSettingGroupResponse(group=group, count=count)
            for group, count in sorted(groups.items())
        ],
        migration_status={
            "legacy_system_setting_keys": manifest.legacy_setting_keys(),
            "has_plugin_settings": bool(manifest.settings),
            "runtime_state_controls_enablement": True,
        },
    )


async def _apply_builtin_plugin_runtime_side_effect(
    *,
    runtime: PluginRuntime,
    plugin_id: str,
    enabled: bool,
) -> PluginRuntimeSideEffectResponse:
    """Apply non-destructive runtime side effects for static built-in plugins."""
    manifest = next(
        (item for item in runtime.manifests(enabled_only=False) if item.id == plugin_id),
        None,
    )
    requested_action = "enable" if enabled else "disable"
    effect = next(
        (
            item.effect
            for item in (manifest.runtime_effects if manifest else [])
            if item.action == requested_action
        ),
        None,
    )
    if effect is None:
        return PluginRuntimeSideEffectResponse(
            action=requested_action,
            status="not_applicable",
            message="No runtime side effect is registered for this static plugin.",
        )

    try:
        if effect == "start_feishu_connector":
            from src.infra.channel.feishu.handler import setup_feishu_handler

            await setup_feishu_handler(
                default_agent=settings.DEFAULT_AGENT,
                show_tools=True,
                plugin_runtime=runtime,
            )
            logger.info("Feishu connector started after Plugin Runtime enable")
            return PluginRuntimeSideEffectResponse(
                action=effect,
                status="succeeded",
                message="Feishu connector startup was requested successfully.",
            )

        if effect == "stop_feishu_connector":
            from src.infra.channel.feishu import stop_feishu_channels

            await stop_feishu_channels()
            logger.info("Feishu connector stopped after Plugin Runtime disable")
            return PluginRuntimeSideEffectResponse(
                action=effect,
                status="succeeded",
                message="Feishu connector stop was requested successfully.",
            )

        return PluginRuntimeSideEffectResponse(
            action=effect,
            status="not_applicable",
            message="No runtime side effect executor is registered for this effect.",
        )
    except Exception as exc:  # noqa: BLE001 - runtime side effect must not corrupt state
        message = str(exc) or exc.__class__.__name__
        logger.warning(
            "Plugin runtime side effect failed for %s after %s: %s",
            plugin_id,
            requested_action,
            message,
        )
        return PluginRuntimeSideEffectResponse(
            action=effect,
            status="failed",
            message=message,
        )


async def _run_plugin_startup_hooks_after_enable(
    request: Request,
    *,
    runtime: PluginRuntime,
    plugin_id: str,
    previous_status: PluginRuntimeStatus,
) -> None:
    if previous_status is PluginRuntimeStatus.ENABLED:
        return
    results = await run_plugin_lifecycle_hooks(
        runtime,
        phase="startup",
        plugin_id=plugin_id,
    )
    if not results:
        return
    previous_results = getattr(request.app.state, "plugin_runtime_hook_results", [])
    request.app.state.plugin_runtime_hook_results = [*previous_results, *results]
    for result in results:
        log_method = logger.info if result.status == "succeeded" else logger.warning
        log_method(
            "Plugin lifecycle hook %s/%s %s after enable in %.1fms%s",
            result.plugin_id,
            result.hook_name,
            result.status,
            result.elapsed_ms,
            f": {result.error}" if result.error else "",
        )


@router.get("/", response_model=PluginRuntimeListResponse)
async def list_plugin_runtime(
    request: Request,
    _: object = Depends(require_permissions("marketplace:read")),
) -> PluginRuntimeListResponse:
    runtime = _get_runtime(request)
    states = runtime.states()
    return PluginRuntimeListResponse(
        plugins=[_state_response(runtime, state) for state in states],
        total=len(states),
        runtime=_runtime_capabilities(),
    )


@router.get("/packages", response_model=PluginPackagesResponse)
async def list_plugin_packages(
    request: Request,
    _: object = Depends(require_permissions("marketplace:read")),
) -> PluginPackagesResponse:
    return _plugin_packages_response(request)


@router.post("/packages/scan", response_model=PluginPackagesResponse)
async def scan_plugin_packages(
    request: Request,
    _: object = Depends(require_permissions("marketplace:admin")),
) -> PluginPackagesResponse:
    from pathlib import Path

    from src.kernel.config.utils import PROJECT_ROOT

    plugin_root = Path(getattr(settings, "PLUGIN_PACKAGE_PATH", "./plugins"))
    data_root = Path(getattr(settings, "PLUGIN_DATA_PATH", "./plugin-data"))
    if not plugin_root.is_absolute():
        plugin_root = PROJECT_ROOT / plugin_root
    if not data_root.is_absolute():
        data_root = PROJECT_ROOT / data_root
    await _refresh_runtime_from_packages(request, plugin_root=plugin_root, data_root=data_root)
    return _plugin_packages_response(request)


@router.get("/packages/archived", response_model=ArchivedPluginPackagesResponse)
async def list_archived_plugin_packages(
    request: Request,
    _: object = Depends(require_permissions("marketplace:read")),
) -> ArchivedPluginPackagesResponse:
    plugin_root, data_root = _configured_plugin_roots()
    try:
        archived = _get_package_lifecycle_service(request).list_archived_packages()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ArchivedPluginPackagesResponse(
        plugin_root=str(plugin_root),
        data_root=str(data_root),
        archived=[_archived_package_response(item) for item in archived],
        total=len(archived),
    )


@router.post("/packages/archived/{archive_id}/restore", response_model=PluginPackageRestoreResponse)
async def restore_archived_plugin_package(
    archive_id: str,
    request: Request,
    user: object = Depends(require_permissions("marketplace:admin")),
) -> PluginPackageRestoreResponse:
    plugin_root, data_root = _configured_plugin_roots()
    try:
        result = _get_package_lifecycle_service(request).restore_archived_package(archive_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    storage = _get_state_storage(request)
    await storage.set_override(
        plugin_id=result.plugin_id,
        status=PluginRuntimeStatus.DISABLED,
        updated_by=getattr(user, "sub", None),
        reason="archived_package_restore",
    )
    await storage.append_audit(
        plugin_id=result.plugin_id,
        action="package_restore",
        previous_status=PluginRuntimeStatus.UNINSTALLED,
        next_status=PluginRuntimeStatus.DISABLED,
        actor_user_id=getattr(user, "sub", None),
        actor_username=getattr(user, "username", None),
        reason=f"restored archived package {archive_id}",
    )
    await _refresh_runtime_from_packages(request, plugin_root=plugin_root, data_root=data_root)
    return PluginPackageRestoreResponse(
        plugin_id=result.plugin_id,
        archive_id=result.archive_id,
        status=result.status,
        archive_path=result.archive_path,
        target_path=result.target_path,
        data_dir=result.data_dir,
        integrity=result.integrity.model_dump(),
        warnings=result.warnings,
    )


@router.post("/packages/import", response_model=PluginPackageImportResponse)
async def import_plugin_package(
    data: PluginPackageImportRequest,
    request: Request,
    user: object = Depends(require_permissions("marketplace:admin")),
) -> PluginPackageImportResponse:
    from pathlib import Path

    from src.kernel.config.utils import PROJECT_ROOT

    plugin_root = Path(getattr(settings, "PLUGIN_PACKAGE_PATH", "./plugins"))
    data_root = Path(getattr(settings, "PLUGIN_DATA_PATH", "./plugin-data"))
    if not plugin_root.is_absolute():
        plugin_root = PROJECT_ROOT / plugin_root
    if not data_root.is_absolute():
        data_root = PROJECT_ROOT / data_root
    service = PluginPackageImportService(plugin_root=plugin_root, data_root=data_root)
    try:
        result = service.import_folder(Path(data.source_path), dry_run=data.dry_run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not data.dry_run:
        storage = _get_state_storage(request)
        await storage.set_override(
            plugin_id=result.plugin_id,
            status=PluginRuntimeStatus.DISABLED,
            updated_by=getattr(user, "sub", None),
            reason="local_folder_package_import",
        )
        await storage.append_audit(
            plugin_id=result.plugin_id,
            action="package_import",
            previous_status=None,
            next_status=PluginRuntimeStatus.DISABLED,
            actor_user_id=getattr(user, "sub", None),
            actor_username=getattr(user, "username", None),
            reason="local folder package imported disabled by default",
        )
        await _refresh_runtime_from_packages(request, plugin_root=plugin_root, data_root=data_root)
    return PluginPackageImportResponse(
        plugin_id=result.plugin_id,
        status=result.status,
        dry_run=result.dry_run,
        source_path=result.source_path,
        target_path=result.target_path,
        data_dir=result.data_dir,
        descriptor=_package_descriptor_response(result.descriptor),
        integrity=result.integrity.model_dump(),
        actions=result.actions,
        warnings=result.warnings,
    )


@router.get("/contribution-states", response_model=PluginRuntimeContributionStatesResponse)
async def list_plugin_runtime_contribution_states(
    request: Request,
) -> PluginRuntimeContributionStatesResponse:
    runtime = _get_runtime(request)
    states = runtime.states()
    return PluginRuntimeContributionStatesResponse(
        plugins=[_contribution_state_response(state) for state in states],
        total=len(states),
    )


@router.get("/contributions", response_model=PluginRuntimeContributionStatesResponse)
async def list_plugin_runtime_contributions(
    request: Request,
) -> PluginRuntimeContributionStatesResponse:
    """Return runtime-filterable plugin contributions for frontend host slots."""
    return await list_plugin_runtime_contribution_states(request)


@router.get("/{plugin_id}", response_model=PluginRuntimePluginResponse)
async def get_plugin_runtime(
    plugin_id: str,
    request: Request,
    _: object = Depends(require_permissions("marketplace:read")),
) -> PluginRuntimePluginResponse:
    runtime = _get_runtime(request)
    return _state_response(runtime, _require_state(runtime, plugin_id))


@router.get("/{plugin_id}/settings", response_model=PluginSettingsResponse)
async def list_plugin_settings(
    plugin_id: str,
    request: Request,
    scope: str = "system",
    subject_id: str | None = None,
    _: object = Depends(require_permissions("settings:manage")),
) -> PluginSettingsResponse:
    runtime = _get_runtime(request)
    state = _require_state(runtime, plugin_id)
    return await _plugin_settings_response(
        state=state,
        service=_settings_service(request),
        scope=scope,
        subject_id=subject_id,
    )


@router.put("/{plugin_id}/settings/{key}", response_model=PluginSettingsResponse)
async def update_plugin_setting(
    plugin_id: str,
    key: str,
    data: PluginSettingUpdate,
    request: Request,
    scope: str = "system",
    subject_id: str | None = None,
    user: object = Depends(require_permissions("settings:manage")),
) -> PluginSettingsResponse:
    runtime = _get_runtime(request)
    state = _require_state(runtime, plugin_id)
    manifest = state.manifest
    if manifest is None:
        raise HTTPException(status_code=409, detail="plugin manifest is unavailable")
    service = _settings_service(request)
    try:
        await service.set_setting(
            manifest,
            key=key,
            value=data.value,
            updated_by=getattr(user, "sub", None),
            scope=scope,
            subject_id=subject_id,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _plugin_settings_response(
        state=state,
        service=service,
        scope=scope,
        subject_id=subject_id,
    )


@router.post("/{plugin_id}/settings/{key}/reset", response_model=PluginSettingsResponse)
async def reset_plugin_setting(
    plugin_id: str,
    key: str,
    request: Request,
    scope: str = "system",
    subject_id: str | None = None,
    _: object = Depends(require_permissions("settings:manage")),
) -> PluginSettingsResponse:
    runtime = _get_runtime(request)
    state = _require_state(runtime, plugin_id)
    manifest = state.manifest
    if manifest is None:
        raise HTTPException(status_code=409, detail="plugin manifest is unavailable")
    service = _settings_service(request)
    try:
        await service.reset_setting(
            manifest,
            key=key,
            scope=scope,
            subject_id=subject_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _plugin_settings_response(
        state=state,
        service=service,
        scope=scope,
        subject_id=subject_id,
    )


@router.post("/{plugin_id}/settings/import-legacy", response_model=PluginSettingsResponse)
async def import_plugin_legacy_settings(
    plugin_id: str,
    request: Request,
    user: object = Depends(require_permissions("settings:manage")),
) -> PluginSettingsResponse:
    runtime = _get_runtime(request)
    state = _require_state(runtime, plugin_id)
    manifest = state.manifest
    if manifest is None:
        raise HTTPException(status_code=409, detail="plugin manifest is unavailable")
    service = _settings_service(request)
    await service.import_legacy(manifest, updated_by=getattr(user, "sub", None))
    return await _plugin_settings_response(state=state, service=service)


@router.get("/{plugin_id}/package-review", response_model=PluginPackageReviewResponse)
async def get_plugin_package_review(
    plugin_id: str,
    request: Request,
    _: object = Depends(require_permissions("marketplace:read")),
) -> PluginPackageReviewResponse:
    runtime = _get_runtime(request)
    state = _require_state(runtime, plugin_id)
    integrity = _installed_package_integrity(state)
    if integrity is None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "plugin_package_review_not_applicable",
                "message": "Only user-installed folder packages use local package review.",
                "plugin_id": plugin_id,
            },
        )
    storage = _get_state_storage(request)
    review = await storage.get_package_review(
        plugin_id=plugin_id,
        package_sha256=integrity.package_sha256,
    )
    return _package_review_response(
        plugin_id=plugin_id,
        integrity=integrity,
        review=review,
    )


@router.post("/{plugin_id}/package-review", response_model=PluginPackageReviewResponse)
async def review_plugin_package(
    plugin_id: str,
    data: PluginPackageReviewRequest,
    request: Request,
    user: object = Depends(require_permissions("marketplace:admin")),
) -> PluginPackageReviewResponse:
    runtime = _get_runtime(request)
    state = _require_state(runtime, plugin_id)
    integrity = _installed_package_integrity(state)
    if integrity is None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "plugin_package_review_not_applicable",
                "message": "Only user-installed folder packages use local package review.",
                "plugin_id": plugin_id,
            },
        )
    storage = _get_state_storage(request)
    review = await storage.set_package_review(
        plugin_id=plugin_id,
        package_sha256=integrity.package_sha256,
        reviewed_by=getattr(user, "sub", None),
        reviewer_username=getattr(user, "username", None),
        reason=data.reason,
    )
    await storage.append_audit(
        plugin_id=plugin_id,
        action="package_review",
        previous_status=state.status,
        next_status=state.status,
        actor_user_id=getattr(user, "sub", None),
        actor_username=getattr(user, "username", None),
        reason=data.reason or f"reviewed package hash {integrity.package_sha256[:12]}",
    )
    return _package_review_response(
        plugin_id=plugin_id,
        integrity=integrity,
        review=review,
    )


@router.post("/{plugin_id}/enable", response_model=PluginRuntimePluginResponse)
async def enable_plugin_runtime(
    plugin_id: str,
    request: Request,
    user: object = Depends(require_permissions("marketplace:admin")),
) -> PluginRuntimePluginResponse:
    runtime = _get_runtime(request)
    try:
        current_state = _require_state(runtime, plugin_id)
        storage = _get_state_storage(request)
        integrity_blocker = await _plugin_enable_integrity_blocker(current_state, storage)
        if integrity_blocker is not None:
            raise HTTPException(status_code=409, detail=integrity_blocker)
        previous_status = current_state.status
        state = runtime.enable_plugin(plugin_id)
        override = await storage.set_override(
            plugin_id=plugin_id,
            status=PluginRuntimeStatus.ENABLED,
            updated_by=getattr(user, "sub", None),
        )
        state = runtime.apply_stored_status(
            plugin_id,
            override.status,
            updated_at=override.updated_at,
            updated_by=override.updated_by,
        )
        await storage.append_audit(
            plugin_id=plugin_id,
            action="enable",
            previous_status=previous_status,
            next_status=state.status,
            actor_user_id=getattr(user, "sub", None),
            actor_username=getattr(user, "username", None),
        )
        await _run_plugin_startup_hooks_after_enable(
            request,
            runtime=runtime,
            plugin_id=plugin_id,
            previous_status=previous_status,
        )
        state = _require_state(runtime, plugin_id)
        runtime_side_effect = await _apply_builtin_plugin_runtime_side_effect(
            runtime=runtime,
            plugin_id=plugin_id,
            enabled=True,
        )
    except PluginRuntimeStateTransitionError as exc:
        raise _state_transition_error(exc) from exc
    return _state_response(
        runtime,
        state,
        runtime_side_effect=runtime_side_effect,
    )


@router.post("/{plugin_id}/disable", response_model=PluginRuntimePluginResponse)
async def disable_plugin_runtime(
    plugin_id: str,
    request: Request,
    user: object = Depends(require_permissions("marketplace:admin")),
) -> PluginRuntimePluginResponse:
    runtime = _get_runtime(request)
    try:
        previous_status = _require_state(runtime, plugin_id).status
        state = runtime.disable_plugin(plugin_id)
        storage = _get_state_storage(request)
        override = await storage.set_override(
            plugin_id=plugin_id,
            status=PluginRuntimeStatus.DISABLED,
            updated_by=getattr(user, "sub", None),
        )
        state = runtime.apply_stored_status(
            plugin_id,
            override.status,
            updated_at=override.updated_at,
            updated_by=override.updated_by,
        )
        await storage.append_audit(
            plugin_id=plugin_id,
            action="disable",
            previous_status=previous_status,
            next_status=state.status,
            actor_user_id=getattr(user, "sub", None),
            actor_username=getattr(user, "username", None),
        )
        runtime_side_effect = await _apply_builtin_plugin_runtime_side_effect(
            runtime=runtime,
            plugin_id=plugin_id,
            enabled=False,
        )
    except PluginRuntimeStateTransitionError as exc:
        raise _state_transition_error(exc) from exc
    return _state_response(
        runtime,
        state,
        runtime_side_effect=runtime_side_effect,
    )


@router.get("/{plugin_id}/audit", response_model=PluginRuntimeAuditResponse)
async def list_plugin_runtime_audit(
    plugin_id: str,
    request: Request,
    limit: int = 20,
    _: object = Depends(require_permissions("marketplace:admin")),
) -> PluginRuntimeAuditResponse:
    runtime = _get_runtime(request)
    _require_state(runtime, plugin_id)
    storage = _get_state_storage(request)
    records = await storage.list_audit(plugin_id=plugin_id, limit=limit)
    return PluginRuntimeAuditResponse(
        plugin_id=plugin_id,
        audit=[_audit_response(record) for record in records],
        total=len(records),
    )


@router.get("/{plugin_id}/resources", response_model=PluginResourcesResponse)
async def list_plugin_resources(
    plugin_id: str,
    request: Request,
    _: object = Depends(require_permissions("marketplace:read")),
) -> PluginResourcesResponse:
    runtime = _get_runtime(request)
    _require_state(runtime, plugin_id)
    resources = runtime.resource_ledger.list(plugin_id=plugin_id)
    return PluginResourcesResponse(
        plugin_id=plugin_id,
        resources=[_resource_response(record) for record in resources],
        total=len(resources),
        resource_types=_resource_type_counts(resources),
    )


def _plugin_data_response(snapshot: PluginDataSnapshot) -> PluginDataResponse:
    return PluginDataResponse(
        plugin_id=snapshot.plugin_id,
        data_dir=snapshot.data_dir,
        exists=snapshot.exists,
        subdirs=snapshot.subdirs,
        defaults_path=snapshot.defaults_path,
        current_path=snapshot.current_path,
        runtime_state_path=snapshot.runtime_state_path,
        file_count=snapshot.file_count,
        total_bytes=snapshot.total_bytes,
        backup_count=snapshot.backup_count,
        last_backup_path=snapshot.last_backup_path,
    )


@router.get("/{plugin_id}/data", response_model=PluginDataResponse)
async def get_plugin_data(
    plugin_id: str,
    request: Request,
    _: object = Depends(require_permissions("marketplace:read")),
) -> PluginDataResponse:
    runtime = _get_runtime(request)
    _require_state(runtime, plugin_id)
    return _plugin_data_response(_get_data_service(request).snapshot(plugin_id))


@router.post("/{plugin_id}/data/reset", response_model=PluginDataResponse)
async def reset_plugin_data_current_config(
    plugin_id: str,
    request: Request,
    user: object = Depends(require_permissions("marketplace:admin")),
) -> PluginDataResponse:
    runtime = _get_runtime(request)
    state = _require_state(runtime, plugin_id)
    snapshot = _get_data_service(request).reset_current_config(plugin_id)
    storage = _get_state_storage(request)
    await storage.append_audit(
        plugin_id=plugin_id,
        action="plugin_data_reset",
        previous_status=state.status,
        next_status=state.status,
        actor_user_id=getattr(user, "sub", None),
        actor_username=getattr(user, "username", None),
        reason="plugin-data current config reset; previous current.json backed up first",
    )
    return _plugin_data_response(snapshot)


@router.get("/{plugin_id}/uninstall-dry-run", response_model=PluginUninstallDryRunResponse)
async def get_plugin_uninstall_dry_run(
    plugin_id: str,
    request: Request,
    _: object = Depends(require_permissions("marketplace:read")),
) -> PluginUninstallDryRunResponse:
    runtime = _get_runtime(request)
    _require_state(runtime, plugin_id)
    dry_run = build_uninstall_dry_run(plugin_id=plugin_id, ledger=runtime.resource_ledger)
    storage = _get_state_storage(request)
    await storage.save_uninstall_dry_run(dry_run=dry_run)
    validation = validate_uninstall_dry_run(
        dry_run,
        plugin_id=plugin_id,
        ledger=runtime.resource_ledger,
    )
    actions = Counter(resource.action.value for resource in dry_run.resources)
    return PluginUninstallDryRunResponse(
        plugin_id=dry_run.plugin_id,
        created_at=dry_run.created_at,
        expires_at=dry_run.expires_at,
        snapshot_id=dry_run.snapshot_id,
        resource_fingerprint=dry_run.resource_fingerprint,
        resource_count=dry_run.resource_count,
        resources=[
            PluginDryRunResourceResponse(
                plugin_id=resource.plugin_id,
                resource_id=resource.resource_id,
                resource_type=resource.resource_type,
                action=resource.action.value,
                retention_policy=resource.retention_policy,
                cleanup_strategy=resource.cleanup_strategy,
                scope=resource.scope,
                requires_confirmation=resource.requires_confirmation,
                irreversible=resource.irreversible,
                reason=resource.reason,
                metadata=resource.metadata,
            )
            for resource in dry_run.resources
        ],
        actions=dict(actions),
        warnings=dry_run.warnings,
        requires_confirmation=dry_run.requires_confirmation,
        rollback_notes=dry_run.rollback_notes,
        package_data_policy=_dry_run_package_data_policy(dry_run),
        validation={
            "allowed": validation.allowed,
            "expired": validation.expired,
            "resource_changed": validation.resource_changed,
            "blockers": validation.blockers,
            "warnings": validation.warnings,
            "checked_at": validation.checked_at,
            "supports_physical_uninstall": True,
        },
    )


@router.get("/{plugin_id}/export", response_model=PluginExportResponse)
async def export_plugin_runtime(
    plugin_id: str,
    request: Request,
    _: object = Depends(require_permissions("marketplace:admin")),
) -> PluginExportResponse:
    runtime = _get_runtime(request)
    state = _require_state(runtime, plugin_id)
    manifest = state.manifest
    resources = runtime.resource_ledger.list(plugin_id=plugin_id)
    dry_run = build_uninstall_dry_run(plugin_id=plugin_id, ledger=runtime.resource_ledger)
    storage = _get_state_storage(request)
    await storage.save_uninstall_dry_run(dry_run=dry_run)
    validation = validate_uninstall_dry_run(
        dry_run,
        plugin_id=plugin_id,
        ledger=runtime.resource_ledger,
        confirmed=True,
    )
    settings_payload: list[dict[str, Any]] = []
    if manifest is not None:
        service = _settings_service(request)
        settings_payload = [
            {
                key: value
                for key, value in item.items()
                if key not in {"legacy_system_setting_keys", "json_schema", "visible_when"}
            }
            for item in await service.export_settings(manifest, mask_sensitive=True)
        ]
    return PluginExportResponse(
        schema_version="lambchat.plugin.export.v1",
        exported_at=datetime.now(UTC),
        plugin_id=plugin_id,
        install_type=manifest.install_type.value if manifest else "not_installed",
        uninstallable=manifest.uninstallable if manifest else False,
        manifest=_manifest_export(manifest),
        runtime_state={
            "status": state.status.value,
            "state_source": state.state_source,
            "state_updated_at": state.state_updated_at,
            "state_updated_by": state.state_updated_by,
        },
        settings=settings_payload,
        resources={
            "total": len(resources),
            "resource_types": _resource_type_counts(resources),
            "records": [_resource_response(record).model_dump(mode="json") for record in resources],
        },
        dry_run=_dry_run_response_dict(dry_run, validation),
        notes=[
            "Sensitive plugin settings are masked and are not exported as secrets.",
            "Import restores known plugin settings/state only; it does not execute remote code or hot-load packages.",
        ],
    )


@router.get("/{plugin_id}/package-export", response_model=PluginPackageExportResponse)
async def export_plugin_package(
    plugin_id: str,
    request: Request,
    _: object = Depends(require_permissions("marketplace:admin")),
) -> PluginPackageExportResponse:
    runtime = _get_runtime(request)
    state = _require_state(runtime, plugin_id)
    manifest = state.manifest
    resources = runtime.resource_ledger.list(plugin_id=plugin_id)
    snapshot = _get_data_service(request).snapshot(plugin_id)
    return PluginPackageExportResponse(
        schema_version="lambchat.plugin.package-export.v1",
        exported_at=datetime.now(UTC),
        plugin_id=plugin_id,
        source_type=manifest.package_source_type if manifest else "not_installed",
        source_path=manifest.package_source_path if manifest else None,
        manifest_path=manifest.package_manifest_path if manifest else None,
        data_dir=manifest.package_data_dir if manifest else None,
        package_summary=_package_summary(manifest),
        manifest=_manifest_export(manifest),
        resources={
            "total": len(resources),
            "resource_types": _resource_type_counts(resources),
            "records": [_resource_response(record).model_dump(mode="json") for record in resources],
        },
        data_snapshot=_plugin_data_response(snapshot).model_dump(mode="json"),
        notes=[
            "This export describes the folder-based plugin package and plugin-data snapshot metadata.",
            "Package summary includes layout and non-sensitive file metadata only; it does not bundle plugin source code.",
            "It is not a remote executable package and does not include sensitive plugin settings.",
        ],
    )


@router.get("/{plugin_id}/package-archive")
async def export_plugin_package_archive(
    plugin_id: str,
    request: Request,
    _: object = Depends(require_permissions("marketplace:admin")),
) -> StreamingResponse:
    runtime = _get_runtime(request)
    state = _require_state(runtime, plugin_id)
    archive_bytes = _package_archive_bytes(state.manifest)
    filename = f"{plugin_id}-plugin-package.zip"
    return StreamingResponse(
        io.BytesIO(archive_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import", response_model=PluginImportResponse)
async def import_plugin_runtime(
    data: PluginImportRequest,
    request: Request,
    user: object = Depends(require_permissions("marketplace:admin")),
) -> PluginImportResponse:
    payload = data.payload
    schema_version = payload.get("schema_version")
    if schema_version != "lambchat.plugin.export.v1":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_plugin_export",
                "message": "Unsupported plugin export schema.",
            },
        )
    plugin_id = str(payload.get("plugin_id") or "")
    if not plugin_id:
        raise HTTPException(status_code=400, detail="plugin_id is required")
    runtime = _get_runtime(request)
    state = _require_state(runtime, plugin_id)
    manifest = state.manifest
    warnings = ["Import does not execute remote code or hot-load plugin packages in this phase."]
    imported_settings: list[str] = []
    skipped_settings: list[str] = []
    if data.import_settings and manifest is not None:
        service = _settings_service(request)
        for item in payload.get("settings", []):
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "")
            value = item.get("value")
            if not key or item.get("sensitive") is True:
                skipped_settings.append(key or "<missing>")
                continue
            try:
                await service.set_setting(
                    manifest,
                    key=key,
                    value=value,
                    scope=str(item.get("scope") or "system"),
                    subject_id=item.get("subject_id"),
                    updated_by=getattr(user, "sub", None),
                )
                imported_settings.append(key)
            except (KeyError, ValueError):
                skipped_settings.append(key)
    if data.restore_state:
        status = payload.get("runtime_state", {}).get("status")
        if status in {"enabled", "disabled"}:
            storage = _get_state_storage(request)
            previous_status = state.status
            override = await storage.set_override(
                plugin_id=plugin_id,
                status=PluginRuntimeStatus(status),
                updated_by=getattr(user, "sub", None),
                reason="plugin_import_restore_state",
            )
            restored = runtime.apply_stored_status(
                plugin_id,
                override.status,
                updated_at=override.updated_at,
                updated_by=override.updated_by,
            )
            await storage.append_audit(
                plugin_id=plugin_id,
                action="import_restore_state",
                previous_status=previous_status,
                next_status=restored.status,
                actor_user_id=getattr(user, "sub", None),
                actor_username=getattr(user, "username", None),
                reason="plugin import requested runtime state restore",
            )
            state = restored
        else:
            warnings.append(
                "Runtime state was not restored because the export state is not controllable."
            )
    return PluginImportResponse(
        plugin_id=plugin_id,
        status=state.status.value,
        imported_settings=imported_settings,
        skipped_settings=skipped_settings,
        warnings=warnings,
    )


@router.post("/{plugin_id}/uninstall", response_model=PluginUninstallResponse)
async def uninstall_plugin_runtime(
    plugin_id: str,
    data: PluginUninstallRequest,
    request: Request,
    user: object = Depends(require_permissions("marketplace:admin")),
) -> PluginUninstallResponse:
    runtime = _get_runtime(request)
    state = _require_state(runtime, plugin_id)
    manifest = state.manifest
    if manifest is None:
        raise HTTPException(status_code=409, detail="plugin manifest is unavailable")
    if not manifest.uninstallable:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "plugin_uninstall_protected",
                "message": "System preset plugins can only be disabled, not uninstalled.",
            },
        )
    storage = _get_state_storage(request)
    dry_run = await storage.get_uninstall_dry_run(
        plugin_id=plugin_id,
        snapshot_id=data.snapshot_id,
    )
    validation = validate_uninstall_dry_run(
        dry_run,
        plugin_id=plugin_id,
        ledger=runtime.resource_ledger,
        confirmed=data.confirmed,
    )
    if not validation.allowed:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "plugin_uninstall_dry_run_invalid",
                "blockers": validation.blockers,
                "warnings": validation.warnings,
            },
        )
    try:
        package_result = _get_package_lifecycle_service(request).uninstall_package(manifest)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "plugin_package_uninstall_rejected",
                "message": str(exc),
            },
        ) from exc
    previous_status = state.status
    try:
        uninstalled = runtime.uninstall_plugin(
            plugin_id,
            updated_by=getattr(user, "sub", None),
        )
    except PluginRuntimeUninstallError as exc:
        raise _uninstall_error(exc) from exc
    override = await storage.set_override(
        plugin_id=plugin_id,
        status=PluginRuntimeStatus.UNINSTALLED,
        updated_by=getattr(user, "sub", None),
        reason=data.reason or "plugin_uninstall",
    )
    uninstalled = runtime.apply_stored_status(
        plugin_id,
        override.status,
        updated_at=override.updated_at,
        updated_by=override.updated_by,
    )
    await storage.append_audit(
        plugin_id=plugin_id,
        action="uninstall",
        previous_status=previous_status,
        next_status=uninstalled.status,
        actor_user_id=getattr(user, "sub", None),
        actor_username=getattr(user, "username", None),
        reason=data.reason,
    )
    response_status = uninstalled.status.value
    if package_result.action == "archive_package_folder":
        plugin_root, data_root = _configured_plugin_roots()
        runtime = await _refresh_runtime_from_packages(
            request,
            plugin_root=plugin_root,
            data_root=data_root,
        )
        refreshed_state = runtime.get_state(plugin_id)
        response_status = (
            refreshed_state.status.value
            if refreshed_state is not None
            else PluginRuntimeStatus.UNINSTALLED.value
        )
    actions = Counter(resource.action.value for resource in dry_run.resources)
    return PluginUninstallResponse(
        plugin_id=plugin_id,
        status=response_status,
        previous_status=previous_status.value,
        snapshot_id=dry_run.snapshot_id,
        actions=dict(actions),
        archived_resources=len(dry_run.will_archive),
        kept_resources=len(dry_run.will_keep),
        deleted_resources=len(dry_run.will_delete),
        package_action=package_result.action,
        package_archive_path=package_result.archive_path,
        plugin_data_retained=package_result.data_retained,
        plugin_data_dir=package_result.data_dir,
        package_integrity=(
            package_result.integrity.model_dump() if package_result.integrity is not None else None
        ),
        warnings=[*validation.warnings, *package_result.warnings],
        audit_action="uninstall",
    )

"""Plugin package manifest merging and response serialization helpers."""

from __future__ import annotations

from src.api.routes.plugin_runtime_models import (
    ArchivedPluginPackageResponse,
    PluginPackageDescriptorResponse,
)
from src.kernel.extensions.packages import PluginFolderDescriptor


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
